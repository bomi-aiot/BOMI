package com.ssafy.bomi.vector.application;

import com.ssafy.bomi.vector.config.QdrantProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

/**
 * Makes sure the Qdrant collections exist, independent of the embedding sync switch
 * (S15P11E102-308).
 *
 * <p><b>Why this bean exists at all.</b> Before this ticket, {@code ensureCollections()} was
 * only ever called from {@code EmbeddingSyncScheduler.prepare()}, and that whole bean is
 * conditional on {@code bomi.embedding.sync-enabled=true}. {@code production.env.example}
 * recommends running with sync disabled on demo day, assuming the collections already exist.
 * On a fresh deploy or a wiped Qdrant volume that assumption is false: nothing ever creates
 * them, the first real search upserts into a missing collection, and
 * {@code QdrantVectorStore.markUnreachable} latches semantic search off until restart — with
 * no exception surfacing, just quietly shallower answers.</p>
 *
 * <p><b>Why the condition is "is a host configured" and not "is sync enabled."</b> Search and
 * sync are different concerns. If semantic search can run at all (a host is configured), the
 * collections it searches against must exist — whether or not the background reindex job is
 * running. Gating on the sync switch tied two unrelated decisions together.</p>
 *
 * <p><b>Why {@code ApplicationReadyEvent} and not {@code @PostConstruct}.</b> Same reasoning
 * {@code EmbeddingSyncScheduler} already used: creating a collection is a network call, and a
 * network call during bean construction can turn a temporarily unreachable Qdrant into a
 * failed application startup. The app must boot without its derived index.</p>
 */
@Component
public class VectorStoreStartupInitializer {

    private static final Logger log = LoggerFactory.getLogger(VectorStoreStartupInitializer.class);

    private final VectorStore vectorStore;
    private final QdrantProperties qdrantProperties;

    public VectorStoreStartupInitializer(VectorStore vectorStore, QdrantProperties qdrantProperties) {
        this.vectorStore = vectorStore;
        this.qdrantProperties = qdrantProperties;
    }

    /**
     * Ensures the {@code memory} and {@code conversation_summary} collections exist once the
     * app is up.
     *
     * <p>Skipped entirely when no Qdrant host is configured. {@code QdrantVectorStore.connect}
     * already logged that semantic search is off in that case; calling {@code ensureCollections}
     * here too would just repeat the same fact. This also means the check is safe on every test
     * and every developer boot with no Qdrant container running — nothing here does I/O unless
     * a host is set.</p>
     */
    @EventListener(ApplicationReadyEvent.class)
    public void ensureCollectionsOnStartup() {
        if (!qdrantProperties.isConfigured()) {
            return;
        }
        // ensureCollections() 자체도 store.isAvailable() 을 다시 확인한다(연결이 실제로
        // 됐는지는 QdrantVectorStore.connect 가 결정한다). 여기서는 "해볼 가치가 있는가"만
        // 판단하고, "됐는가"는 그 안에서 판단한다.
        vectorStore.ensureCollections();
        log.info("vector store collections ensured at startup (independent of "
            + "bomi.embedding.sync-enabled)");
    }
}
