package com.ssafy.bomi.observability;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.context.application.DocumentCorpusSearch;
import com.ssafy.bomi.context.config.DocumentCorpusProperties;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.embedding.application.EmbeddingClient;
import com.ssafy.bomi.embedding.config.EmbeddingProperties;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.vector.application.VectorStore;
import com.ssafy.bomi.vector.config.QdrantProperties;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;

class RagHealthIndicatorTest {

    private EmbeddingProperties embeddingProperties;
    private QdrantProperties qdrantProperties;
    private DocumentCorpusProperties documentProperties;
    private EmbeddingClient embeddingClient;
    private VectorStore vectorStore;
    private DocumentCorpusSearch documentSearch;
    private MemoryRepository memoryRepository;
    private ConversationSummaryRepository summaryRepository;

    @BeforeEach
    void setUp() {
        embeddingProperties = new EmbeddingProperties();
        qdrantProperties = new QdrantProperties();
        documentProperties = new DocumentCorpusProperties();
        embeddingClient = mock(EmbeddingClient.class);
        vectorStore = mock(VectorStore.class);
        documentSearch = mock(DocumentCorpusSearch.class);
        memoryRepository = mock(MemoryRepository.class);
        summaryRepository = mock(ConversationSummaryRepository.class);
        when(documentSearch.isAvailable()).thenReturn(true);
    }

    @Test
    void intentionalKeywordFallbackIsHealthyWhenTheBundledCorpusIsReady() {
        Health health = indicator().health();

        assertThat(health.getStatus().getCode()).isEqualTo("UP");
        assertThat(health.getDetails()).containsEntry("semanticMode", "keyword_fallback")
            .containsEntry("documentCorpusAvailable", true);
    }

    @Test
    void configuredButUnavailableSemanticSearchIsDegraded() {
        embeddingProperties.setEnabled(true);
        qdrantProperties.setHost("qdrant");

        Health health = indicator().health();

        assertThat(health.getStatus().getCode()).isEqualTo("DEGRADED");
        assertThat(health.getDetails()).containsEntry("embeddingAvailable", false)
            .containsEntry("qdrantAvailable", false);
    }

    @Test
    void failedEmbeddingRowsAreVisibleAsDegradedBacklog() {
        when(memoryRepository.countByEmbeddingStatus(EmbeddingStatus.FAILED)).thenReturn(2L);

        Health health = indicator().health();

        assertThat(health.getStatus().getCode()).isEqualTo("DEGRADED");
        @SuppressWarnings("unchecked")
        var rows = (java.util.Map<String, Long>) health.getDetails().get("embeddingRows");
        assertThat(rows).containsEntry("failed", 2L);
    }

    private RagHealthIndicator indicator() {
        return new RagHealthIndicator(
            embeddingProperties, qdrantProperties, documentProperties, embeddingClient,
            vectorStore, documentSearch, memoryRepository, summaryRepository);
    }
}
