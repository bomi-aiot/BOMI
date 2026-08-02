package com.ssafy.bomi.context.application;

import com.ssafy.bomi.embedding.application.EmbeddingClient;
import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore;
import java.util.List;
import java.util.UUID;
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
    public List<SemanticHit> search(UUID seniorId, String query, int limit) {
        if (!isAvailable() || query == null || query.isBlank() || limit <= 0) {
            // 빈 질의로 임베딩을 부르지 않는다. 과금되는 호출이고, 비교 기준이 없는 턴에서
            // 얻을 것이 없다. 호출부(loadSimilarities)도 같은 판단을 하지만, 여기서 한 번
            // 더 막는다 — 새 호출부가 생겼을 때 돈이 새는 쪽으로 기본값이 서지 않게 한다.
            return List.of();
        }

        float[] queryVector;
        try {
            // ★ embedQuery 다. embedPassage 를 쓰면 예외 없이 조금 더 나쁜 이웃이
            //   영원히 나오고, 그 사실을 알려주는 것이 시스템에 아무것도 없다.
            queryVector = embeddingClient.embedQuery(query);
        } catch (EmbeddingClient.EmbeddingFailedException error) {
            // 턴을 죽이지 않는다. 얕은 랭킹으로 대답하는 편이, 색인 때문에 어르신을
            // 침묵 앞에 두는 것보다 낫다.
            log.warn("could not embed the query; ranking without semantic scores", error);
            return List.of();
        }

        return vectorStore.search(VectorCollection.MEMORY, seniorId, queryVector, limit)
            .stream()
            .map(hit -> new SemanticHit(hit.id(), hit.score()))
            .toList();
    }
}
