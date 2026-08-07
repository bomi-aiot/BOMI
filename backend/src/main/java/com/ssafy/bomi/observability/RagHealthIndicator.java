package com.ssafy.bomi.observability;

import com.ssafy.bomi.context.application.DocumentCorpusSearch;
import com.ssafy.bomi.context.config.DocumentCorpusProperties;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.embedding.application.EmbeddingClient;
import com.ssafy.bomi.embedding.config.EmbeddingProperties;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.vector.application.VectorStore;
import com.ssafy.bomi.vector.config.QdrantProperties;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.boot.actuate.health.Status;
import org.springframework.stereotype.Component;

/** Operational readiness of RAG, embedding, Qdrant and synchronization backlog. */
@Component("rag")
public class RagHealthIndicator implements HealthIndicator {

    private static final Status DEGRADED = new Status("DEGRADED");

    private final EmbeddingProperties embeddingProperties;
    private final QdrantProperties qdrantProperties;
    private final DocumentCorpusProperties documentProperties;
    private final EmbeddingClient embeddingClient;
    private final VectorStore vectorStore;
    private final DocumentCorpusSearch documentSearch;
    private final MemoryRepository memoryRepository;
    private final ConversationSummaryRepository summaryRepository;

    public RagHealthIndicator(EmbeddingProperties embeddingProperties,
        QdrantProperties qdrantProperties,
        DocumentCorpusProperties documentProperties,
        EmbeddingClient embeddingClient,
        VectorStore vectorStore,
        DocumentCorpusSearch documentSearch,
        MemoryRepository memoryRepository,
        ConversationSummaryRepository summaryRepository) {
        this.embeddingProperties = embeddingProperties;
        this.qdrantProperties = qdrantProperties;
        this.documentProperties = documentProperties;
        this.embeddingClient = embeddingClient;
        this.vectorStore = vectorStore;
        this.documentSearch = documentSearch;
        this.memoryRepository = memoryRepository;
        this.summaryRepository = summaryRepository;
    }

    @Override
    public Health health() {
        try {
            boolean semanticExpected = embeddingProperties.isEnabled()
                || qdrantProperties.isConfigured();
            boolean embeddingAvailable = embeddingClient.isAvailable();
            boolean qdrantAvailable = vectorStore.isAvailable();
            boolean semanticReady = embeddingAvailable && qdrantAvailable;
            boolean documentAvailable = documentSearch.isAvailable();
            Map<EmbeddingStatus, Long> backlog = backlog();

            boolean degraded = (semanticExpected && !semanticReady)
                || (documentProperties.isEnabled() && !documentAvailable)
                || backlog.get(EmbeddingStatus.FAILED) > 0;
            Health.Builder builder = degraded ? Health.status(DEGRADED) : Health.up();
            return builder
                .withDetail("semanticMode", semanticReady ? "qdrant" : "keyword_fallback")
                .withDetail("embeddingEnabled", embeddingProperties.isEnabled())
                .withDetail("embeddingAvailable", embeddingAvailable)
                .withDetail("qdrantConfigured", qdrantProperties.isConfigured())
                .withDetail("qdrantAvailable", qdrantAvailable)
                .withDetail("documentCorpusEnabled", documentProperties.isEnabled())
                .withDetail("documentCorpusAvailable", documentAvailable)
                .withDetail("embeddingRows", statusDetails(backlog))
                .build();
        } catch (RuntimeException error) {
            return Health.down(error).withDetail("reason", "rag_health_query_failed").build();
        }
    }

    private Map<EmbeddingStatus, Long> backlog() {
        Map<EmbeddingStatus, Long> counts = new EnumMap<>(EmbeddingStatus.class);
        for (EmbeddingStatus status : EmbeddingStatus.values()) {
            counts.put(status, memoryRepository.countByEmbeddingStatus(status)
                + summaryRepository.countByEmbeddingStatus(status));
        }
        return counts;
    }

    private Map<String, Long> statusDetails(Map<EmbeddingStatus, Long> backlog) {
        Map<String, Long> details = new LinkedHashMap<>();
        for (EmbeddingStatus status : EmbeddingStatus.values()) {
            details.put(status.name().toLowerCase(), backlog.get(status));
        }
        return details;
    }
}
