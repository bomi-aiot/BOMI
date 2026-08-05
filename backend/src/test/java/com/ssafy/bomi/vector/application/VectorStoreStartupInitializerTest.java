package com.ssafy.bomi.vector.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.vector.config.QdrantProperties;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * The startup guard, with a fake store — no Qdrant needed (S15P11E102-308).
 *
 * <p>What this proves is narrower than the {@code integration}-tagged sibling test: only that
 * the initializer calls (or does not call) {@code ensureCollections()} depending on whether a
 * host is configured. Whether Qdrant actually creates the collections is a different question,
 * answered by {@code VectorStoreStartupInitializerIntegrationTest} against a real server.</p>
 */
class VectorStoreStartupInitializerTest {

    @Test
    @DisplayName("★ 호스트가 설정돼 있으면 ensureCollections 를 부른다 (동기화 스위치와 무관)")
    void callsEnsureCollectionsWhenHostIsConfigured() {
        RecordingVectorStore store = new RecordingVectorStore();
        QdrantProperties properties = new QdrantProperties();
        properties.setHost("localhost");

        new VectorStoreStartupInitializer(store, properties).ensureCollectionsOnStartup();

        assertThat(store.ensureCollectionsCalls).isEqualTo(1);
    }

    @Test
    @DisplayName("호스트가 비어 있으면 아무것도 하지 않는다")
    void doesNothingWhenNoHostIsConfigured() {
        /*
         * QdrantVectorStore.connect() 가 이미 "호스트 없음 = 의미 검색 OFF" 를 기동 로그에
         * 남긴다. 여기서 다시 ensureCollections() 를 부르면 같은 사실을 두 번 알리는
         * 것도 문제지만, 더 중요한 것은 이 테스트가 증명하는 바다 — 개발 노트북처럼
         * Qdrant 컨테이너가 아예 없는 환경에서 이 빈이 네트워크 호출을 시도하지
         * 않는다는 것.
         */
        RecordingVectorStore store = new RecordingVectorStore();
        QdrantProperties properties = new QdrantProperties();
        // host 기본값은 "" — 명시적으로 다시 비워 의도를 드러낸다.
        properties.setHost("");

        new VectorStoreStartupInitializer(store, properties).ensureCollectionsOnStartup();

        assertThat(store.ensureCollectionsCalls).isZero();
    }

    /** Counts calls; never touches a network. */
    private static class RecordingVectorStore implements VectorStore {
        int ensureCollectionsCalls = 0;

        @Override
        public void ensureCollections() {
            ensureCollectionsCalls++;
        }

        @Override
        public VectorWriteStatus upsert(VectorCollection collection, UUID id, UUID seniorId,
            float[] vector) {
            return VectorWriteStatus.STORED;
        }

        @Override
        public List<VectorHit> search(VectorCollection collection, UUID seniorId,
            float[] queryVector, int limit) {
            return List.of();
        }

        @Override
        public void delete(VectorCollection collection, UUID id) {
        }

        @Override
        public boolean isAvailable() {
            return false;
        }
    }
}
