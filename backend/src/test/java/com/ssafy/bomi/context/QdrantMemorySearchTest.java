package com.ssafy.bomi.context;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.context.application.MemorySemanticSearch.SemanticHit;
import com.ssafy.bomi.context.application.MemorySemanticSearch.SearchResult;
import com.ssafy.bomi.context.application.QdrantMemorySearch;
import com.ssafy.bomi.embedding.application.EmbeddingClient;
import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore;
import com.ssafy.bomi.vector.application.VectorStore.VectorSearchResult;
import com.ssafy.bomi.vector.application.VectorStore.VectorSearchStatus;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * The query side of semantic search (S15P11E102-218). No network, no cost.
 *
 * <p>Three things are pinned here, and each one fails <em>silently</em> in production if it
 * regresses — which is exactly why they need a test rather than a code review:</p>
 * <ol>
 *   <li>the query model is used for queries, not the passage model;</li>
 *   <li>a blank query never reaches the metered API;</li>
 *   <li>a failure anywhere degrades the ranking instead of failing the turn.</li>
 * </ol>
 */
class QdrantMemorySearchTest {

    private static final UUID SENIOR = UUID.randomUUID();

    // ── 대역 ─────────────────────────────────────────────────────────────────

    /** Records which model was asked for. That is the whole point of this fake. */
    private static class RecordingEmbeddingClient implements EmbeddingClient {
        final List<String> calls = new ArrayList<>();
        boolean available = true;
        boolean explode = false;

        @Override
        public float[] embedPassage(String text) {
            calls.add("passage:" + text);
            return vector();
        }

        @Override
        public float[] embedQuery(String text) {
            calls.add("query:" + text);
            if (explode) {
                throw new EmbeddingFailedException("upstream is down");
            }
            return vector();
        }

        private float[] vector() {
            return new float[] {0.1f, 0.2f, 0.3f};
        }

        @Override
        public String passageModelId() {
            return "embedding-passage";
        }

        @Override
        public int dimensions() {
            return 3;
        }

        @Override
        public boolean isAvailable() {
            return available;
        }
    }

    private static class StubVectorStore implements VectorStore {
        List<VectorHit> memoryHits = List.of();
        List<VectorHit> summaryHits = List.of();
        VectorSearchStatus searchStatus = VectorSearchStatus.COMPLETED;
        boolean available = true;
        int searchCount = 0;
        int lastLimit = -1;

        @Override
        public void ensureCollections() {
        }

        @Override
        public VectorWriteStatus upsert(VectorCollection collection, UUID id, UUID seniorId,
            float[] vector) {
            return VectorWriteStatus.STORED;
        }

        @Override
        public VectorSearchResult search(VectorCollection collection, UUID seniorId,
            float[] queryVector, int limit) {
            searchCount++;
            lastLimit = limit;
            List<VectorHit> hits = collection == VectorCollection.MEMORY
                ? memoryHits : summaryHits;
            return new VectorSearchResult(hits, searchStatus);
        }

        @Override
        public void delete(VectorCollection collection, UUID id) {
        }

        @Override
        public boolean isAvailable() {
            return available;
        }
    }

    // ── 1. 질의는 query 모델로 ───────────────────────────────────────────────

    @Test
    @DisplayName("★ 질의는 embedQuery 로 임베딩한다 — passage 를 쓰면 조용히 나빠진다")
    void aQueryIsEmbeddedWithTheQueryModel() {
        /*
         * ★★ 이 둘을 섞어도 예외가 나지 않는다. 조금 더 나쁜 이웃이 영원히 나올 뿐이고,
         *    시스템 안에 그것을 알려주는 장치가 없다. 그래서 테스트로 고정한다.
         *    Upstage 는 저장용(-passage)과 검색용(-query) 모델을 짝으로 학습시킨다.
         */
        RecordingEmbeddingClient embedding = new RecordingEmbeddingClient();
        StubVectorStore store = new StubVectorStore();
        QdrantMemorySearch search = new QdrantMemorySearch(store, embedding);

        search.search(SENIOR, "무릎이 아파", 5, 0);

        assertThat(embedding.calls).containsExactly("query:무릎이 아파");
    }

    @Test
    void hitsArePassedThroughWithTheirScores() {
        UUID memoryId = UUID.randomUUID();
        RecordingEmbeddingClient embedding = new RecordingEmbeddingClient();
        StubVectorStore store = new StubVectorStore();
        store.memoryHits = List.of(new VectorStore.VectorHit(memoryId, 0.87));
        QdrantMemorySearch search = new QdrantMemorySearch(store, embedding);

        SearchResult result = search.search(SENIOR, "무릎", 5, 0);

        assertThat(result.memoryHits()).containsExactly(new SemanticHit(memoryId, 0.87));
        assertThat(result.semanticUsed()).isTrue();
        assertThat(result.fallbackReason()).isNull();
        assertThat(result.embeddingLatencyMs()).isNotNegative();
        assertThat(result.vectorSearchLatencyMs()).isNotNegative();
        assertThat(result.latencyMs())
            .isGreaterThanOrEqualTo(result.embeddingLatencyMs());
        assertThat(store.lastLimit).isEqualTo(5);
    }

    @Test
    @DisplayName("기억과 요약을 한 번 임베딩해 각 컬렉션에서 함께 찾는다")
    void memoryAndSummarySearchShareOneQueryEmbedding() {
        UUID memoryId = UUID.randomUUID();
        UUID summaryId = UUID.randomUUID();
        RecordingEmbeddingClient embedding = new RecordingEmbeddingClient();
        StubVectorStore store = new StubVectorStore();
        store.memoryHits = List.of(new VectorStore.VectorHit(memoryId, 0.9));
        store.summaryHits = List.of(new VectorStore.VectorHit(summaryId, 0.8));
        QdrantMemorySearch search = new QdrantMemorySearch(store, embedding);

        SearchResult result = search.search(SENIOR, "낚시", 5, 3);

        assertThat(embedding.calls).containsExactly("query:낚시");
        assertThat(store.searchCount).isEqualTo(2);
        assertThat(result.memoryHits()).containsExactly(new SemanticHit(memoryId, 0.9));
        assertThat(result.summaryHits()).containsExactly(new SemanticHit(summaryId, 0.8));
        assertThat(result.semanticUsed()).isTrue();
    }

    // ── 2. 과금되는 호출을 낭비하지 않는다 ───────────────────────────────────

    @Test
    @DisplayName("★ 빈 질의는 과금되는 API 에 도달하지 않는다")
    void ablankQueryNeverReachesTheMeteredApi() {
        /*
         * 발화가 없는 턴(스케줄 제안 등)에는 비교 기준이 없다. 그래도 호출하면 매번
         * 돈을 쓰고 아무것도 얻지 못한다. 잔액이 프로토타입 시연까지 감당해야 한다.
         */
        RecordingEmbeddingClient embedding = new RecordingEmbeddingClient();
        StubVectorStore store = new StubVectorStore();
        QdrantMemorySearch search = new QdrantMemorySearch(store, embedding);

        assertThat(search.search(SENIOR, "", 5, 0).semanticUsed()).isFalse();
        assertThat(search.search(SENIOR, "   ", 5, 0).semanticUsed()).isFalse();
        assertThat(search.search(SENIOR, null, 5, 0).semanticUsed()).isFalse();
        assertThat(search.search(SENIOR, "무릎", 0, 0).semanticUsed()).isFalse();

        assertThat(embedding.calls).isEmpty();
        assertThat(store.searchCount).isZero();
    }

    @Test
    void nothingIsCalledWhenTheStoreOrTheModelIsUnavailable() {
        RecordingEmbeddingClient embedding = new RecordingEmbeddingClient();
        StubVectorStore store = new StubVectorStore();
        QdrantMemorySearch search = new QdrantMemorySearch(store, embedding);

        store.available = false;
        assertThat(search.search(SENIOR, "무릎", 5, 0).fallbackReason())
            .isEqualTo("semantic_unavailable");
        assertThat(search.isAvailable()).isFalse();

        store.available = true;
        embedding.available = false;
        assertThat(search.search(SENIOR, "무릎", 5, 0).fallbackReason())
            .isEqualTo("semantic_unavailable");
        assertThat(search.isAvailable()).isFalse();

        assertThat(embedding.calls).isEmpty();
    }

    // ── 3. 실패해도 턴은 살아남는다 ──────────────────────────────────────────

    @Test
    @DisplayName("★ 임베딩이 실패해도 예외를 올리지 않는다 — 침묵보다 얕은 랭킹이 낫다")
    void anEmbeddingFailureDegradesRankingInsteadOfFailingTheTurn() {
        /*
         * 어르신 앞에서 로봇이 대답을 못 하는 이유가 '색인이 죽어서'여서는 안 된다.
         * 의미 점수 없이 키워드·중요도·최근성으로 답하는 편이 낫다.
         */
        RecordingEmbeddingClient embedding = new RecordingEmbeddingClient();
        embedding.explode = true;
        StubVectorStore store = new StubVectorStore();
        QdrantMemorySearch search = new QdrantMemorySearch(store, embedding);

        SearchResult result = search.search(SENIOR, "무릎", 5, 0);

        assertThat(result.semanticUsed()).isFalse();
        assertThat(result.fallbackReason()).isEqualTo("embedding_failed");
        assertThat(result.embeddingLatencyMs()).isNotNegative();
        assertThat(result.vectorSearchLatencyMs()).isZero();
        assertThat(store.searchCount)
            .as("임베딩이 없으면 검색할 벡터도 없다")
            .isZero();
    }

    @Test
    @DisplayName("0건 성공과 Qdrant 실패를 서로 다른 상태로 반환한다")
    void emptySuccessAndVectorFailureAreDistinguishable() {
        RecordingEmbeddingClient embedding = new RecordingEmbeddingClient();
        StubVectorStore store = new StubVectorStore();
        QdrantMemorySearch search = new QdrantMemorySearch(store, embedding);

        SearchResult empty = search.search(SENIOR, "무릎", 5, 0);
        assertThat(empty.semanticUsed()).isTrue();
        assertThat(empty.memoryHits()).isEmpty();
        assertThat(empty.fallbackReason()).isNull();

        store.searchStatus = VectorSearchStatus.FAILED;
        SearchResult failed = search.search(SENIOR, "무릎", 5, 0);
        assertThat(failed.semanticUsed()).isFalse();
        assertThat(failed.fallbackReason()).isEqualTo("memory_vector_search_failed");
    }
}
