package com.ssafy.bomi.context.application;

import com.ssafy.bomi.embedding.application.EmbeddingClient;
import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore;
import com.ssafy.bomi.vector.application.VectorStore.VectorSearchResult;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;

/**
 * Semantic memory search over the external vector store (S15P11E102-218).
 *
 * <p>Replaces {@link NoVectorStoreMemorySearch}, which returned nothing and said so. That
 * class is kept rather than deleted: it is the fallback the {@code @Primary} annotation
 * here is chosen over, and it documents what "unavailable" is supposed to look like.</p>
 *
 * <p><b>This class returns ids and scores. It never returns memory content.</b> That is the
 * privacy design, not a simplification. {@code ConversationContextService} loads the
 * retrievable set from PostgreSQL first and uses these scores only to <em>rank</em> it, so a
 * memory whose {@code visibility} or {@code lifecycle_status} changed after it was indexed
 * cannot come back on the strength of a stale payload. If this method returned text, the
 * shortest path to "answer the turn" would bypass that check.</p>
 *
 * <p><b>Two ways to be unavailable, both fine.</b> No API key (cannot embed the query) or no
 * Qdrant (nowhere to search). Either way {@link #isAvailable()} is false, the assembly ranks
 * by keyword × importance × recency, and the response tells the robot semantic ranking did
 * not run — a handler that thinks it searched everything speaks about the past with more
 * confidence than it earned.</p>
 */
@Component
@Primary
public class QdrantMemorySearch implements MemorySemanticSearch {

    private static final Logger log = LoggerFactory.getLogger(QdrantMemorySearch.class);

    private final VectorStore vectorStore;
    private final EmbeddingClient embeddingClient;

    public QdrantMemorySearch(VectorStore vectorStore, EmbeddingClient embeddingClient) {
        this.vectorStore = vectorStore;
        this.embeddingClient = embeddingClient;
    }

    @Override
    public boolean isAvailable() {
        return vectorStore.isAvailable() && embeddingClient.isAvailable();
    }

    @Override
    public SearchResult search(UUID seniorId, String query, int memoryLimit, int summaryLimit) {
        long startedAt = System.nanoTime();
        if (!isAvailable()) {
            return result(List.of(), List.of(), false, "semantic_unavailable", startedAt, 0, 0);
        }
        if (query == null || query.isBlank()) {
            // 빈 질의로 임베딩을 부르지 않는다. 과금되는 호출이고, 비교 기준이 없는 턴에서
            // 얻을 것이 없다. 호출부(loadSimilarities)도 같은 판단을 하지만, 여기서 한 번
            // 더 막는다 — 새 호출부가 생겼을 때 돈이 새는 쪽으로 기본값이 서지 않게 한다.
            return result(List.of(), List.of(), false, "query_blank", startedAt, 0, 0);
        }
        if (memoryLimit <= 0 && summaryLimit <= 0) {
            return result(List.of(), List.of(), false, "no_candidates", startedAt, 0, 0);
        }

        float[] queryVector;
        long embeddingStartedAt = System.nanoTime();
        try {
            // ★ embedQuery 다. embedPassage 를 쓰면 예외 없이 조금 더 나쁜 이웃이
            //   영원히 나오고, 그 사실을 알려주는 것이 시스템에 아무것도 없다.
            queryVector = embeddingClient.embedQuery(query);
        } catch (EmbeddingClient.EmbeddingFailedException error) {
            // 턴을 죽이지 않는다. 얕은 랭킹으로 대답하는 편이, 색인 때문에 어르신을
            // 침묵 앞에 두는 것보다 낫다.
            log.warn("could not embed the query; ranking without semantic scores", error);
            return result(List.of(), List.of(), false, "embedding_failed", startedAt,
                elapsedMillis(embeddingStartedAt), 0);
        }
        long embeddingLatencyMs = elapsedMillis(embeddingStartedAt);

        long vectorSearchStartedAt = System.nanoTime();
        VectorSearchResult memories = memoryLimit > 0
            ? vectorStore.search(VectorCollection.MEMORY, seniorId, queryVector, memoryLimit)
            : null;
        VectorSearchResult summaries = summaryLimit > 0
            ? vectorStore.search(VectorCollection.CONVERSATION_SUMMARY, seniorId, queryVector,
                summaryLimit)
            : null;
        long vectorSearchLatencyMs = elapsedMillis(vectorSearchStartedAt);

        List<SemanticHit> memoryHits = toSemanticHits(memories);
        List<SemanticHit> summaryHits = toSemanticHits(summaries);
        boolean memoryUsed = memories != null && memories.completed();
        boolean summaryUsed = summaries != null && summaries.completed();
        boolean used = memoryUsed || summaryUsed;
        String fallbackReason = fallbackReason(memories, summaries);
        return result(memoryHits, summaryHits, used, fallbackReason, startedAt,
            embeddingLatencyMs, vectorSearchLatencyMs);
    }

    private List<SemanticHit> toSemanticHits(VectorSearchResult result) {
        if (result == null || !result.completed()) {
            return List.of();
        }
        return result.hits().stream()
            .map(hit -> new SemanticHit(hit.id(), hit.score()))
            .toList();
    }

    private String fallbackReason(VectorSearchResult memories, VectorSearchResult summaries) {
        String memoryFailure = failureReason("memory", memories);
        String summaryFailure = failureReason("summary", summaries);
        if (memoryFailure != null && summaryFailure != null) {
            return "memory_and_summary_" + commonFailure(memories, summaries);
        }
        return memoryFailure != null ? memoryFailure : summaryFailure;
    }

    private String failureReason(String collection, VectorSearchResult result) {
        if (result == null || result.completed()) {
            return null;
        }
        return switch (result.status()) {
            case UNAVAILABLE -> collection + "_vector_unavailable";
            case FAILED -> collection + "_vector_search_failed";
            case DIMENSION_MISMATCH -> collection + "_vector_dimension_mismatch";
            case COMPLETED -> null;
        };
    }

    private String commonFailure(VectorSearchResult memories, VectorSearchResult summaries) {
        if (memories.status() == summaries.status()) {
            return switch (memories.status()) {
                case UNAVAILABLE -> "vector_unavailable";
                case FAILED -> "vector_search_failed";
                case DIMENSION_MISMATCH -> "vector_dimension_mismatch";
                case COMPLETED -> "semantic_failed";
            };
        }
        return "vector_search_partial_failure";
    }

    private SearchResult result(List<SemanticHit> memories, List<SemanticHit> summaries,
        boolean used, String fallbackReason, long startedAt, long embeddingLatencyMs,
        long vectorSearchLatencyMs) {
        long latencyMs = elapsedMillis(startedAt);
        return new SearchResult(memories, summaries, used, fallbackReason, latencyMs,
            embeddingLatencyMs, vectorSearchLatencyMs);
    }

    private long elapsedMillis(long startedAt) {
        return TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedAt);
    }
}
