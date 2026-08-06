package com.ssafy.bomi.observability;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.embedding.application.EmbeddingSyncService.SyncReport;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class RagMetricsTest {

    @Test
    void retrievalSyncAndBacklogMetricsShareStableTags() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MemoryRepository memories = mock(MemoryRepository.class);
        ConversationSummaryRepository summaries = mock(ConversationSummaryRepository.class);
        when(memories.countByEmbeddingStatus(EmbeddingStatus.PENDING)).thenReturn(3L);
        when(summaries.countByEmbeddingStatus(EmbeddingStatus.PENDING)).thenReturn(2L);
        RagMetrics metrics = new RagMetrics(registry, memories, summaries);

        metrics.recordRetrieval("semantic", true, false, "embedding_failed", 0, 12);
        metrics.recordRetrieval("document", true, true, null, 3, 4);
        metrics.recordEmbeddingSync(new SyncReport(2, 1, 1, 1, false));

        assertThat(registry.get("bomi.rag.retrieval.requests")
            .tags("kind", "semantic", "outcome", "fallback", "reason", "embedding_failed")
            .counter().count()).isEqualTo(1.0);
        assertThat(registry.get("bomi.rag.retrieval.fallbacks")
            .tags("kind", "semantic", "reason", "embedding_failed")
            .counter().count()).isEqualTo(1.0);
        assertThat(registry.get("bomi.rag.retrieval.hits").tag("kind", "document")
            .summary().totalAmount()).isEqualTo(3.0);
        assertThat(registry.get("bomi.embedding.sync.billed.calls").counter().count())
            .isEqualTo(5.0);
        assertThat(registry.get("bomi.embedding.rows").tag("status", "pending")
            .gauge().value()).isEqualTo(5.0);
    }
}
