package com.ssafy.bomi.vector.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.abort;

import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore.VectorHit;
import com.ssafy.bomi.vector.application.VectorStore.VectorWriteStatus;
import com.ssafy.bomi.vector.config.QdrantProperties;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/**
 * The Qdrant adapter against a real server (S15P11E102-218). <b>No API cost.</b>
 *
 * <p><b>Why this is tagged and excluded from {@code ./gradlew test}.</b> Qdrant is a Rust
 * server with no embedded mode — there is no {@code embedded-postgres} equivalent — and
 * Testcontainers needs Docker, which not every machine here has. Excluding it keeps the
 * default suite runnable everywhere. Run it with:</p>
 *
 * <pre>QDRANT_HOST=localhost ./gradlew integrationTest</pre>
 *
 * <p><b>The vectors are fake and that is deliberate.</b> Everything asserted here is about
 * the <em>store</em>: that a 4096-dimension collection gets created with an HNSW index, that
 * an upsert comes back from a search, that the senior filter holds, that a wipe is
 * recoverable. None of that needs a real embedding model, and the embedding API is metered
 * against a balance that also has to cover the prototype demo. The real model is exercised
 * exactly twice, in {@code UpstageEmbeddingBilledTest}.</p>
 *
 * <p>When {@code QDRANT_HOST} is unset the test <b>aborts loudly</b> rather than passing.
 * A skipped test that reports green is how an unverified completion condition gets ticked
 * off.</p>
 */
@Tag("integration")
@DisplayName("Qdrant 실제 서버 왕복 (과금 없음)")
class QdrantVectorStoreIntegrationTest {

    /** 4096 — the number that made pgvector impossible and this store necessary. */
    private static final int DIMENSIONS = 4096;

    private static QdrantVectorStore store;
    private static QdrantProperties properties;

    @BeforeAll
    static void connect() {
        String host = System.getProperty("bomi.test.qdrant.host", "");
        if (host.isBlank()) {
            abort("QDRANT_HOST 가 없습니다. 이 테스트는 실제 Qdrant 를 요구합니다 "
                + "(QDRANT_HOST=localhost ./gradlew integrationTest). "
                + "건너뛴 것을 통과로 읽지 마십시오.");
        }

        properties = new QdrantProperties();
        properties.setHost(host);
        properties.setGrpcPort(Integer.parseInt(
            System.getProperty("bomi.test.qdrant.grpcPort", "6334")));
        properties.setDimensions(DIMENSIONS);
        // 실제 서버 왕복은 로컬 인메모리보다 느리다. 턴 예산용 1.5초를 그대로 쓰면
        // 첫 컬렉션 생성에서 간헐적으로 터진다.
        properties.setTimeoutMillis(10_000);

        store = new QdrantVectorStore(properties);
        store.connect();
        store.ensureCollections();
    }

    @AfterAll
    static void disconnect() {
        if (store != null) {
            store.disconnect();
        }
    }

    // ── 완료 조건: 4096차원 컬렉션과 HNSW ────────────────────────────────────

    @Test
    @DisplayName("★ 컬렉션 2개가 4096차원으로 만들어진다")
    void bothCollectionsExistAtTheRightDimension() {
        /*
         * ★★ 이 티켓의 출발점이 이것이다. pgvector 는 4096차원에 인덱스를 만들 수
         *    없다(상한 vector 2,000 / halfvec 4,000). 여기서 실제로 만들어지는 것을
         *    확인하지 않으면, "옮겼다"는 주장에 근거가 없다.
         *
         * ensureCollections 는 @BeforeAll 에서 돌았다. 여기서는 결과를 본다 —
         * 차원이 맞으면 업서트가 받아들여지고, 틀리면 거부된다.
         */
        UUID senior = UUID.randomUUID();
        UUID id = UUID.randomUUID();

        for (VectorCollection collection : VectorCollection.values()) {
            assertThat(store.upsert(collection, id, senior, unitVector(0)))
                .isEqualTo(VectorWriteStatus.STORED);
            List<VectorHit> hits = store.search(collection, senior, unitVector(0), 1).hits();
            assertThat(hits)
                .as("%s 컬렉션이 4096차원 업서트를 받아들여야 한다", collection.collectionName())
                .isNotEmpty();
            store.delete(collection, id);
        }
    }

    @Test
    @DisplayName("★ 차원이 틀린 벡터는 서버에 보내기 전에 막는다")
    void awrongSizedVectorIsRejectedLocally() {
        /*
         * gRPC 오류 메시지만 남으면 원인이 '모델을 바꿨다'라는 사실에서 멀어진다.
         * 여기서 막고 로그에 모델과 설정이 어긋났다고 적는다.
         */
        UUID senior = UUID.randomUUID();
        UUID id = UUID.randomUUID();

        assertThat(store.upsert(VectorCollection.MEMORY, id, senior,
            new float[] {1.0f, 0.0f}))
            .isEqualTo(VectorWriteStatus.DIMENSION_MISMATCH);

        assertThat(store.search(VectorCollection.MEMORY, senior, unitVector(0), 5).hits())
            .isEmpty();
    }

    // ── 완료 조건: 저장 → 검색 왕복 ─────────────────────────────────────────

    @Test
    @DisplayName("★ 저장한 벡터가 검색으로 돌아오고, 가까운 것이 앞에 온다")
    void storedVectorsComeBackInSimilarityOrder() {
        UUID senior = UUID.randomUUID();
        UUID near = UUID.randomUUID();
        UUID far = UUID.randomUUID();

        // 축이 다른 두 단위 벡터. 코사인 거리에서 서로 직교한다.
        store.upsert(VectorCollection.MEMORY, near, senior, unitVector(0));
        store.upsert(VectorCollection.MEMORY, far, senior, unitVector(1));

        List<VectorHit> hits = store.search(VectorCollection.MEMORY, senior,
            unitVector(0), 5).hits();

        assertThat(hits).extracting(VectorHit::id).containsExactly(near, far);
        assertThat(hits.get(0).score())
            .as("자기 자신과의 코사인 유사도는 1 에 가깝다")
            .isCloseTo(1.0, org.assertj.core.data.Offset.offset(0.001));
        assertThat(hits.get(1).score())
            .as("직교하면 0 에 가깝다 — 점수가 importance·recency 와 곱해질 수 있는 범위여야 한다")
            .isCloseTo(0.0, org.assertj.core.data.Offset.offset(0.001));

        store.delete(VectorCollection.MEMORY, near);
        store.delete(VectorCollection.MEMORY, far);
    }

    @Test
    @DisplayName("어르신 필터가 다른 어르신의 벡터를 걸러낸다")
    void theSeniorFilterKeepsHouseholdsApart() {
        /*
         * 이 필터는 효율을 위한 것이고 프라이버시 경계가 아니다(경계는 Postgres
         * 재검증이다 — SemanticHitsDoNotBypassTheAuthorityFilterTest). 그래도 동작해야
         * 한다: 없으면 모든 질의가 모든 어르신의 기억과 점수를 겨룬다.
         */
        UUID mine = UUID.randomUUID();
        UUID theirs = UUID.randomUUID();
        UUID myPoint = UUID.randomUUID();
        UUID theirPoint = UUID.randomUUID();

        store.upsert(VectorCollection.MEMORY, myPoint, mine, unitVector(0));
        store.upsert(VectorCollection.MEMORY, theirPoint, theirs, unitVector(0));

        assertThat(store.search(VectorCollection.MEMORY, mine, unitVector(0), 10).hits())
            .extracting(VectorHit::id)
            .containsExactly(myPoint);

        store.delete(VectorCollection.MEMORY, myPoint);
        store.delete(VectorCollection.MEMORY, theirPoint);
    }

    // ── 완료 조건: 전부 지운 뒤 재색인으로 복구 ─────────────────────────────

    @Test
    @DisplayName("★ 벡터를 지우면 검색에서 사라지고, 다시 넣으면 돌아온다")
    void deletingAndReindexingIsSymmetric() {
        /*
         * ★★ "Qdrant 데이터를 전부 지운 뒤 부기 컬럼 기준으로 재색인이 복구되는 것"의
         *    스토어 쪽 절반이다. 부기 쪽 절반은 EmbeddingSyncServiceTest 에 있다
         *    (wipingTheVectorStoreIsRecoverableFromTheBookkeepingColumns).
         *
         *    둘을 합치면: 볼륨을 잃어도 복구된다 → 그래서 백업 대상이 아니다.
         */
        UUID senior = UUID.randomUUID();
        UUID id = UUID.randomUUID();

        store.upsert(VectorCollection.MEMORY, id, senior, unitVector(0));
        assertThat(store.search(VectorCollection.MEMORY, senior, unitVector(0), 5).hits())
            .isNotEmpty();

        store.delete(VectorCollection.MEMORY, id);
        assertThat(store.search(VectorCollection.MEMORY, senior, unitVector(0), 5).hits())
            .isEmpty();

        store.upsert(VectorCollection.MEMORY, id, senior, unitVector(0));
        assertThat(store.search(VectorCollection.MEMORY, senior, unitVector(0), 5).hits())
            .extracting(VectorHit::id).containsExactly(id);

        store.delete(VectorCollection.MEMORY, id);
    }

    @Test
    @DisplayName("같은 id 를 다시 업서트하면 행이 늘지 않고 대체된다")
    void anupsertReplacesRatherThanDuplicates() {
        /*
         * 재색인은 업서트를 반복한다. 늘어난다면 한 기억이 여러 점수로 여러 번
         * 후보에 오르고, 상위 k 가 한 기억으로 채워진다.
         */
        UUID senior = UUID.randomUUID();
        UUID id = UUID.randomUUID();

        store.upsert(VectorCollection.MEMORY, id, senior, unitVector(0));
        store.upsert(VectorCollection.MEMORY, id, senior, unitVector(1));

        List<VectorHit> hits = store.search(VectorCollection.MEMORY, senior,
            unitVector(1), 10).hits();
        assertThat(hits).hasSize(1);
        assertThat(hits.get(0).score()).isCloseTo(1.0, org.assertj.core.data.Offset.offset(0.001));

        store.delete(VectorCollection.MEMORY, id);
    }

    // ── ensureCollections 는 멱등이고, 절대 지우지 않는다 ───────────────────

    @Test
    @DisplayName("★ ensureCollections 를 다시 불러도 기존 벡터가 살아 있다")
    void ensureCollectionsNeverDropsWhatIsAlreadyThere() {
        /*
         * ★★ recreateCollection 은 한 줄로 차원 불일치를 '고치고' 그 과정에서 모든
         *    벡터를 버린다. 설정 오타 하나가 그 가구의 전체 재색인이 되고, 그것은
         *    전액 재과금이다. 그래서 어댑터는 불일치를 보고만 하고 고치지 않는다.
         */
        UUID senior = UUID.randomUUID();
        UUID id = UUID.randomUUID();
        store.upsert(VectorCollection.MEMORY, id, senior, unitVector(0));

        store.ensureCollections();

        assertThat(store.search(VectorCollection.MEMORY, senior, unitVector(0), 5).hits())
            .extracting(VectorHit::id).containsExactly(id);

        store.delete(VectorCollection.MEMORY, id);
    }

    /** A unit vector along one axis. Free, deterministic, and 4096 long. */
    private static float[] unitVector(int axis) {
        float[] vector = new float[DIMENSIONS];
        vector[axis] = 1.0f;
        return vector;
    }
}
