package com.ssafy.bomi.vector.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore.VectorWriteStatus;
import com.ssafy.bomi.vector.config.QdrantProperties;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** Qdrant 서버 없이도 검증할 수 있는 벡터 쓰기 계약. */
class QdrantVectorStoreWriteContractTest {

    @Test
    @DisplayName("호스트가 없으면 저장 성공을 가장하지 않고 UNAVAILABLE 을 반환한다")
    void unavailableStoreReturnsAnExplicitFailure() {
        QdrantProperties properties = propertiesWithTwoDimensions();
        QdrantVectorStore store = new QdrantVectorStore(properties);

        VectorWriteStatus result = store.upsert(VectorCollection.MEMORY,
            UUID.randomUUID(), UUID.randomUUID(), new float[] {1.0f, 0.0f});

        assertThat(result).isEqualTo(VectorWriteStatus.UNAVAILABLE);
    }

    @Test
    @DisplayName("잘못된 차원은 네트워크 호출 전에 DIMENSION_MISMATCH 로 거부한다")
    void dimensionMismatchIsReportedBeforeAnyNetworkCall() {
        QdrantProperties properties = propertiesWithTwoDimensions();
        QdrantVectorStore store = new QdrantVectorStore(properties);

        VectorWriteStatus result = store.upsert(VectorCollection.MEMORY,
            UUID.randomUUID(), UUID.randomUUID(), new float[] {1.0f});

        assertThat(result).isEqualTo(VectorWriteStatus.DIMENSION_MISMATCH);
    }

    private QdrantProperties propertiesWithTwoDimensions() {
        QdrantProperties properties = new QdrantProperties();
        properties.setDimensions(2);
        return properties;
    }
}
