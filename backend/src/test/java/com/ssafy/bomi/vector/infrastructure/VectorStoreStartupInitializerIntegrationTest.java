package com.ssafy.bomi.vector.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.abort;

import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore.VectorHit;
import com.ssafy.bomi.vector.application.VectorStore.VectorWriteStatus;
import com.ssafy.bomi.vector.application.VectorStoreStartupInitializer;
import com.ssafy.bomi.vector.config.QdrantProperties;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

/**
 * Collection creation split from the sync switch, against a real server (S15P11E102-308).
 * <b>No API cost.</b>
 *
 * <p><b>What this proves that {@code QdrantVectorStoreIntegrationTest} does not.</b> That test
 * calls {@code store.ensureCollections()} directly in {@code @BeforeAll} — it was never
 * exercising the question this ticket is about, which is <em>who calls it in production</em>.
 * Before this ticket the only caller was {@code EmbeddingSyncScheduler.prepare()}, gated by
 * {@code bomi.embedding.sync-enabled=true}. This test never touches that scheduler at all — it
 * starts from an empty collection state and only calls {@link VectorStoreStartupInitializer},
 * the same way {@code ApplicationReadyEvent} would with sync disabled — and shows the
 * collections still get created.</p>
 *
 * <p>Same package as {@code QdrantVectorStoreIntegrationTest} on purpose: both need
 * {@code QdrantVectorStore.connect()} / {@code disconnect()}, which are package-private so
 * production code cannot call them outside the {@code @PostConstruct} / {@code @PreDestroy}
 * lifecycle.</p>
 *
 * <p>Run with:</p>
 *
 * <pre>QDRANT_HOST=localhost ./gradlew integrationTest</pre>
 *
 * <p>Same reasoning as the sibling test for why this is tagged and excluded from
 * {@code ./gradlew test}: Qdrant has no embedded mode, and not every developer machine here has
 * Docker for Testcontainers. When {@code QDRANT_HOST} is unset this aborts loudly rather than
 * passing — a skipped test that reports green is how an unverified completion condition gets
 * ticked off.</p>
 */
@Tag("integration")
@DisplayName("컬렉션 생성이 동기화 스위치와 분리되어 있다 (S15P11E102-308)")
class VectorStoreStartupInitializerIntegrationTest {

    /** 4096 — the number that made pgvector impossible and this store necessary. */
    private static final int DIMENSIONS = 4096;

    private static QdrantVectorStore store;
    private static VectorStoreStartupInitializer initializer;

    @BeforeAll
    static void connect() {
        String host = System.getProperty("bomi.test.qdrant.host", "");
        if (host.isBlank()) {
            abort("QDRANT_HOST 가 없습니다. 이 테스트는 실제 Qdrant 를 요구합니다 "
                + "(QDRANT_HOST=localhost ./gradlew integrationTest). "
                + "건너뛴 것을 통과로 읽지 마십시오.");
        }

        QdrantProperties properties = new QdrantProperties();
        properties.setHost(host);
        properties.setGrpcPort(Integer.parseInt(
            System.getProperty("bomi.test.qdrant.grpcPort", "6334")));
        properties.setDimensions(DIMENSIONS);
        // 실제 서버 왕복은 로컬 인메모리보다 느리다. 턴 예산용 1.5초를 그대로 쓰면
        // 첫 컬렉션 생성에서 간헐적으로 터진다.
        properties.setTimeoutMillis(10_000);

        store = new QdrantVectorStore(properties);
        store.connect();
        // ★ 여기서 store.ensureCollections() 를 직접 부르지 않는다. 이 테스트가
        //   확인하려는 것이 정확히 "EmbeddingSyncScheduler 없이도 컬렉션이 생기는가"
        //   이기 때문이다 — 직접 부르면 그 질문 자체를 우회하게 된다.
        initializer = new VectorStoreStartupInitializer(store, properties);
    }

    @AfterAll
    static void disconnect() {
        if (store != null) {
            store.disconnect();
        }
    }

    @Test
    @DisplayName(
        "★ EMBEDDING_SYNC_ENABLED=false 를 흉내내도(스케줄러 없이도) 컬렉션 2개가 생긴다")
    void collectionsAreCreatedWithoutTheSyncScheduler() {
        /*
         * ★★ 이 티켓의 출발점이다. 308 이전에는 ensureCollections() 를 부르는 유일한
         *    경로가 sync-enabled=true 일 때만 존재하는 EmbeddingSyncScheduler 뿐이었다.
         *    그 빈을 아예 만들지 않고(이 테스트가 하는 그대로) initializer 만으로
         *    컬렉션이 생기는지 확인한다.
         */
        initializer.ensureCollectionsOnStartup();

        UUID senior = UUID.randomUUID();
        UUID id = UUID.randomUUID();
        for (VectorCollection collection : VectorCollection.values()) {
            assertThat(store.upsert(collection, id, senior, unitVector(0)))
                .isEqualTo(VectorWriteStatus.STORED);
            List<VectorHit> hits = store.search(collection, senior, unitVector(0), 1);
            assertThat(hits)
                .as("%s 컬렉션이 존재해야 업서트가 검색으로 돌아온다", collection.collectionName())
                .isNotEmpty();
            store.delete(collection, id);
        }
    }

    @Test
    @DisplayName("★ 컬렉션이 준비된 뒤 첫 질의를 보내도 스토어가 OFF 로 래치되지 않는다")
    void theStoreDoesNotLatchOffAfterTheFirstRealQuery() {
        /*
         * ★★ 컬렉션이 없는 채로 upsert 를 보내면 QdrantVectorStore.markUnreachable 이
         *    reachable=false 로 래치하고, 재시작 전까지 의미 검색이 영구히 꺼진다 —
         *    이것이 308 배경 설명의 "첫 질의가 조용히 스토어를 꺼뜨린다"는 증상이다.
         *    이 테스트는 그 증상이 재현되지 않는다는 것을 보인다.
         */
        initializer.ensureCollectionsOnStartup();

        UUID senior = UUID.randomUUID();
        UUID id = UUID.randomUUID();
        assertThat(store.upsert(VectorCollection.MEMORY, id, senior, unitVector(0)))
            .isEqualTo(VectorWriteStatus.STORED);
        store.search(VectorCollection.MEMORY, senior, unitVector(0), 1);
        store.delete(VectorCollection.MEMORY, id);

        assertThat(store.isAvailable())
            .as("컬렉션이 없었다면 위 upsert 가 실패해 markUnreachable 이 이미 래치했을 것이다")
            .isTrue();
    }

    /** A unit vector along one axis. Free, deterministic, and 4096 long. */
    private static float[] unitVector(int axis) {
        float[] vector = new float[DIMENSIONS];
        vector[axis] = 1.0f;
        return vector;
    }
}
