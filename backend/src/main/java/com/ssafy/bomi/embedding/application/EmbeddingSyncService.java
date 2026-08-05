package com.ssafy.bomi.embedding.application;

import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.embedding.config.EmbeddingProperties;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.observability.RagMetrics;
import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore;
import com.ssafy.bomi.vector.application.VectorStore.VectorWriteStatus;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * Keeps the vector store in step with PostgreSQL (S15P11E102-218).
 *
 * <p><b>PostgreSQL is the authority; this store is a derived index.</b> That single sentence
 * decides everything here. It is why losing the Qdrant volume is recoverable, why the
 * bookkeeping columns exist at all (V5), and why this service never writes content back into
 * the database — it only records <em>whether</em> a row has been indexed and by which
 * model.</p>
 *
 * <p><b>Never on the turn path.</b> Embedding yesterday's memory while the senior waits for
 * an answer spends their patience on our housekeeping (CLAUDE.md §18). The only embedding
 * call inside a turn is the query one, in {@code QdrantMemorySearch}.</p>
 *
 * <p><b>Bounded by design, because the API is metered.</b> One row is one billed call, and
 * the project balance also has to cover the prototype demo. Three separate brakes:</p>
 * <ul>
 *   <li>the batch size caps calls per run;</li>
 *   <li>{@code FAILED} rows are not retried by default, so a permanently broken row cannot
 *       be paid for every five minutes forever;</li>
 *   <li>the job is off unless switched on.</li>
 * </ul>
 *
 * <p>A run that cannot reach the store or the model does nothing at all rather than marking
 * rows {@code FAILED} — "the store was down" is not the same as "this row cannot be
 * embedded", and conflating them would burn the retry budget of healthy rows.</p>
 */
@Service
public class EmbeddingSyncService {

    private static final Logger log = LoggerFactory.getLogger(EmbeddingSyncService.class);

    /**
     * What a normal run picks up.
     *
     * <p>{@code FAILED} is absent on purpose — see {@link #retryFailed()} for the deliberate
     * way to include it.</p>
     */
    private static final Set<EmbeddingStatus> DUE =
        Set.of(EmbeddingStatus.PENDING, EmbeddingStatus.STALE);

    private static final Set<EmbeddingStatus> DUE_WITH_FAILED =
        Set.of(EmbeddingStatus.PENDING, EmbeddingStatus.STALE, EmbeddingStatus.FAILED);

    private enum IndexOutcome {
        INDEXED,
        FAILED,
        DEFERRED
    }

    private final MemoryRepository memoryRepository;
    private final ConversationSummaryRepository summaryRepository;
    private final EmbeddingClient embeddingClient;
    private final VectorStore vectorStore;
    private final EmbeddingProperties properties;
    private final RagMetrics ragMetrics;

    /**
     * One transaction per row, opened explicitly.
     *
     * <p><b>Why not {@code @Transactional} on the per-row methods.</b> They are called from
     * {@link #sync} inside this same bean, and a self-invocation does not pass through the
     * Spring proxy — the annotation would sit there, read correctly in review, and do
     * nothing at all. That is a bad thing to leave in place even where the effect happens to
     * be small.</p>
     *
     * <p><b>What the boundary actually buys.</b> {@code embed → upsert → save} becomes one
     * unit per row, so a row that throws cannot undo the bookkeeping of rows already paid
     * for. Without it the three steps would run under whatever transaction the caller
     * happened to have; from the scheduler that is none, and {@code save()} would still
     * commit on its own (Spring Data's own {@code @Transactional}), but a caller that
     * <em>did</em> have one would make the whole batch all-or-nothing. The API calls are
     * spent either way, so an all-or-nothing rollback means paying for them twice.</p>
     */
    private final TransactionTemplate transactions;

    @Autowired
    public EmbeddingSyncService(MemoryRepository memoryRepository,
        ConversationSummaryRepository summaryRepository,
        EmbeddingClient embeddingClient,
        VectorStore vectorStore,
        EmbeddingProperties properties,
        PlatformTransactionManager transactionManager,
        RagMetrics ragMetrics) {
        this.memoryRepository = memoryRepository;
        this.summaryRepository = summaryRepository;
        this.embeddingClient = embeddingClient;
        this.vectorStore = vectorStore;
        this.properties = properties;
        this.transactions = new TransactionTemplate(transactionManager);
        this.ragMetrics = ragMetrics;
    }

    /** Test-friendly constructor; production wiring always supplies metrics. */
    public EmbeddingSyncService(MemoryRepository memoryRepository,
        ConversationSummaryRepository summaryRepository,
        EmbeddingClient embeddingClient,
        VectorStore vectorStore,
        EmbeddingProperties properties,
        PlatformTransactionManager transactionManager) {
        this(memoryRepository, summaryRepository, embeddingClient, vectorStore, properties,
            transactionManager, null);
    }

    /** What one run did. Returned so the scheduler can log it and tests can assert it. */
    public record SyncReport(int memoriesIndexed, int summariesIndexed, int failed,
                             int deferred, boolean skipped) {

        /** A run that did nothing because the store or the model was unreachable. */
        static SyncReport unavailable() {
            return new SyncReport(0, 0, 0, 0, true);
        }

        public int billedCalls() {
            return memoriesIndexed + summariesIndexed + failed + deferred;
        }
    }

    /** One ordinary run: {@code PENDING} and {@code STALE} rows, up to the batch cap. */
    public SyncReport syncDue() {
        return sync(DUE);
    }

    /**
     * Also retries {@code FAILED} rows.
     *
     * <p>Separate entry point rather than a flag on the schedule, because a failure is
     * usually permanent (content the model rejects) and retrying it on every tick pays for
     * the same error indefinitely. Someone deciding to retry is a deliberate act.</p>
     */
    public SyncReport retryFailed() {
        return sync(DUE_WITH_FAILED);
    }

    private SyncReport sync(Set<EmbeddingStatus> statuses) {
        if (!embeddingClient.isAvailable() || !vectorStore.isAvailable()) {
            // 행을 FAILED 로 표시하지 않는다. '스토어가 죽었다'와 '이 행은 임베딩할 수
            // 없다'는 다른 사실이고, 섞으면 멀쩡한 행들이 재시도 예산을 잃는다.
            log.debug("embedding sync skipped: embedding={} vectorStore={}",
                embeddingClient.isAvailable(), vectorStore.isAvailable());
            return record(SyncReport.unavailable());
        }

        PageRequest page = PageRequest.of(0, Math.max(1, properties.getSyncBatchSize()));
        int memories = 0;
        int summaries = 0;
        int failed = 0;
        int deferred = 0;

        for (Memory memory : memoryRepository.findNeedingEmbedding(statuses, page)) {
            switch (indexMemory(memory)) {
                case INDEXED -> memories++;
                case FAILED -> failed++;
                case DEFERRED -> deferred++;
            }
        }
        // 남은 예산만큼만 요약을 처리한다. 두 종류가 각자 batchSize 만큼 쓰면 한 번에
        // 두 배가 과금된다 — 상한이 상한이 아니게 된다.
        int remaining = properties.getSyncBatchSize() - (memories + failed + deferred);
        if (remaining > 0) {
            PageRequest summaryPage = PageRequest.of(0, remaining);
            for (ConversationSummary summary
                : summaryRepository.findNeedingEmbedding(statuses, summaryPage)) {
                switch (indexSummary(summary)) {
                    case INDEXED -> summaries++;
                    case FAILED -> failed++;
                    case DEFERRED -> deferred++;
                }
            }
        }

        if (memories + summaries + failed + deferred > 0) {
            log.info("embedding sync: {} memories, {} summaries indexed, {} failed, "
                    + "{} deferred "
                    + "({} billed calls, cap {})",
                memories, summaries, failed, deferred,
                memories + summaries + failed + deferred,
                properties.getSyncBatchSize());
        }
        return record(new SyncReport(memories, summaries, failed, deferred, false));
    }

    private SyncReport record(SyncReport report) {
        if (ragMetrics != null) {
            ragMetrics.recordEmbeddingSync(report);
        }
        return report;
    }

    /**
     * Embeds and stores one memory, then records that it happened.
     *
     * <p>Own transaction per row. One row failing must not roll back the ones already paid
     * for — those calls are spent whether or not the transaction commits, and losing the
     * bookkeeping means paying for them again.</p>
     *
     * <p>The embedding call itself is inside the transaction, which is normally worth
     * avoiding. It is accepted here because the alternative — call outside, write inside —
     * has a window where the process can die after paying and before recording, and that
     * window costs money rather than correctness. The transaction is short and this job is
     * the only writer of these columns.</p>
     */
    private IndexOutcome indexMemory(Memory memory) {
        return transactions.execute(status -> indexMemoryInTx(memory));
    }

    private IndexOutcome indexMemoryInTx(Memory memory) {
        float[] vector;
        try {
            vector = embeddingClient.embedPassage(memory.getContent());
        } catch (RuntimeException error) {
            log.warn("could not embed memory {}; marking it FAILED so it stays visible "
                + "instead of being retried as if it were new", memory.getId(), error);
            memory.markEmbeddingFailed();
            memoryRepository.save(memory);
            return IndexOutcome.FAILED;
        }

        VectorWriteStatus writeStatus;
        try {
            writeStatus = vectorStore.upsert(VectorCollection.MEMORY, memory.getId(),
                memory.getSeniorId(), vector);
        } catch (RuntimeException error) {
            log.error("unexpected vector-store failure for memory {}; keeping status {} for "
                + "reindex", memory.getId(), memory.getEmbeddingStatus(), error);
            return IndexOutcome.DEFERRED;
        }
        if (!writeStatus.stored()) {
            return handleMemoryWriteFailure(memory, writeStatus);
        }

        memory.markEmbeddingSynced(embeddingClient.passageModelId(), OffsetDateTime.now());
        memoryRepository.save(memory);
        return IndexOutcome.INDEXED;
    }

    private IndexOutcome handleMemoryWriteFailure(Memory memory,
        VectorWriteStatus writeStatus) {
        if (writeStatus.retryable()) {
            log.warn("vector write for memory {} was {}; keeping status {} for automatic "
                    + "reindex", memory.getId(), writeStatus, memory.getEmbeddingStatus());
            return IndexOutcome.DEFERRED;
        }
        log.error("vector write for memory {} was {}; marking it FAILED until configuration "
            + "is corrected and retryFailed is run", memory.getId(), writeStatus);
        memory.markEmbeddingFailed();
        memoryRepository.save(memory);
        return IndexOutcome.FAILED;
    }

    private IndexOutcome indexSummary(ConversationSummary summary) {
        return transactions.execute(status -> indexSummaryInTx(summary));
    }

    private IndexOutcome indexSummaryInTx(ConversationSummary summary) {
        float[] vector;
        try {
            vector = embeddingClient.embedPassage(summary.getContent());
        } catch (RuntimeException error) {
            log.warn("could not embed summary {}; marking it FAILED", summary.getId(), error);
            summary.markEmbeddingFailed();
            summaryRepository.save(summary);
            return IndexOutcome.FAILED;
        }

        VectorWriteStatus writeStatus;
        try {
            writeStatus = vectorStore.upsert(VectorCollection.CONVERSATION_SUMMARY,
                summary.getId(), summary.getSeniorId(), vector);
        } catch (RuntimeException error) {
            log.error("unexpected vector-store failure for summary {}; keeping status {} for "
                + "reindex", summary.getId(), summary.getEmbeddingStatus(), error);
            return IndexOutcome.DEFERRED;
        }
        if (!writeStatus.stored()) {
            return handleSummaryWriteFailure(summary, writeStatus);
        }

        summary.markEmbeddingSynced(embeddingClient.passageModelId(), OffsetDateTime.now());
        summaryRepository.save(summary);
        return IndexOutcome.INDEXED;
    }

    private IndexOutcome handleSummaryWriteFailure(ConversationSummary summary,
        VectorWriteStatus writeStatus) {
        if (writeStatus.retryable()) {
            log.warn("vector write for summary {} was {}; keeping status {} for automatic "
                    + "reindex", summary.getId(), writeStatus, summary.getEmbeddingStatus());
            return IndexOutcome.DEFERRED;
        }
        log.error("vector write for summary {} was {}; marking it FAILED until configuration "
            + "is corrected and retryFailed is run", summary.getId(), writeStatus);
        summary.markEmbeddingFailed();
        summaryRepository.save(summary);
        return IndexOutcome.FAILED;
    }

    /**
     * Marks everything embedded by a different model stale.
     *
     * <p>Costs nothing — no API calls, one UPDATE per table. The re-embedding then happens
     * through the ordinary capped runs. Called at startup so a model change cannot leave
     * vectors from two different vector spaces being compared to each other, which produces
     * plausible-looking similarity numbers that mean nothing.</p>
     */
    @Transactional
    public void markStaleAfterModelChange() {
        if (!embeddingClient.isAvailable()) {
            return;
        }
        String model = embeddingClient.passageModelId();
        int memories = memoryRepository.markStaleForOtherModels(model);
        int summaries = summaryRepository.markStaleForOtherModels(model);
        if (memories + summaries > 0) {
            log.warn("embedding model is now '{}': marked {} memories and {} summaries STALE. "
                    + "They will be re-embedded {} rows at a time, which is {} billed calls "
                    + "in total.",
                model, memories, summaries, properties.getSyncBatchSize(), memories + summaries);
        }
    }
}
