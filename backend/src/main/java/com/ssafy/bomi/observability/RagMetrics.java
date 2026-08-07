package com.ssafy.bomi.observability;

import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.embedding.application.EmbeddingSyncService.SyncReport;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import org.springframework.stereotype.Component;

/** Metrics shared by request retrieval and background embedding synchronization. */
@Component
public class RagMetrics {

    private final MeterRegistry registry;
    private final MemoryRepository memoryRepository;
    private final ConversationSummaryRepository summaryRepository;

    public RagMetrics(MeterRegistry registry, MemoryRepository memoryRepository,
        ConversationSummaryRepository summaryRepository) {
        this.registry = registry;
        this.memoryRepository = memoryRepository;
        this.summaryRepository = summaryRepository;
        for (EmbeddingStatus status : EmbeddingStatus.values()) {
            Gauge.builder("bomi.embedding.rows", this, metrics -> metrics.countRows(status))
                .description("PostgreSQL rows by derived-vector synchronization status")
                .tag("status", status.name().toLowerCase())
                .register(registry);
        }
    }

    public void recordRetrieval(String kind, boolean requested, boolean used,
        String fallbackReason, int hitCount, long latencyMs) {
        String outcome = outcome(requested, used, fallbackReason);
        String reason = fallbackReason == null ? "none" : fallbackReason;
        registry.counter("bomi.rag.retrieval.requests",
            "kind", kind, "outcome", outcome, "reason", reason).increment();
        if ("fallback".equals(outcome) || "partial".equals(outcome)) {
            registry.counter("bomi.rag.retrieval.fallbacks",
                "kind", kind, "reason", reason).increment();
        }
        DistributionSummary.builder("bomi.rag.retrieval.hits")
            .description("Authoritative hits attached to one context response")
            .tag("kind", kind)
            .register(registry)
            .record(hitCount);
        Timer.builder("bomi.rag.retrieval.latency")
            .description("Retrieval stage latency reported by the search adapter")
            .tag("kind", kind)
            .tag("outcome", outcome)
            .register(registry)
            .record(Duration.ofMillis(Math.max(0, latencyMs)));
    }

    public void recordEmbeddingSync(SyncReport report) {
        registry.counter("bomi.embedding.sync.runs",
            "outcome", report.skipped() ? "skipped" : "completed").increment();
        incrementRows("memory", "indexed", report.memoriesIndexed());
        incrementRows("summary", "indexed", report.summariesIndexed());
        incrementRows("combined", "failed", report.failed());
        incrementRows("combined", "deferred", report.deferred());
        registry.counter("bomi.embedding.sync.billed.calls")
            .increment(report.billedCalls());
    }

    public void recordRetrievalStage(String stage, boolean requested, long latencyMs) {
        if (!requested) {
            return;
        }
        Timer.builder("bomi.rag.retrieval.stage.latency")
            .description("Latency of one semantic-retrieval sub-stage")
            .tag("stage", stage)
            .register(registry)
            .record(Duration.ofMillis(Math.max(0, latencyMs)));
    }

    private void incrementRows(String type, String outcome, int count) {
        if (count > 0) {
            registry.counter("bomi.embedding.sync.rows", "type", type, "outcome", outcome)
                .increment(count);
        }
    }

    private String outcome(boolean requested, boolean used, String fallbackReason) {
        if (!requested) {
            return "not_requested";
        }
        if (used && fallbackReason != null) {
            return "partial";
        }
        if (used) {
            return "used";
        }
        return "fallback";
    }

    private double countRows(EmbeddingStatus status) {
        try {
            return memoryRepository.countByEmbeddingStatus(status)
                + summaryRepository.countByEmbeddingStatus(status);
        } catch (RuntimeException error) {
            // A scrape must not fail the application request thread. NaN exposes the gap.
            return Double.NaN;
        }
    }
}
