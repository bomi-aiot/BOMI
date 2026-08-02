package com.ssafy.bomi.embedding.infrastructure;

import com.ssafy.bomi.embedding.application.EmbeddingClient;
import com.ssafy.bomi.embedding.config.EmbeddingProperties;
import jakarta.annotation.PostConstruct;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * Upstage embedding adapter (S15P11E102-218).
 *
 * <p><b>Why Upstage and not something cheaper.</b> Korean quality. Every user of this system
 * speaks Korean, and a multilingual model that is 90% as good produces memory retrieval that
 * is subtly wrong in a way nobody notices — the robot brings up the almost-relevant memory.
 * That judgement is what forced 4096 dimensions, which is what forced the vector store out
 * of PostgreSQL in the first place.</p>
 *
 * <p><b>Every call is counted and logged.</b> The API is metered against a small prepaid
 * balance that also has to cover the prototype demo. A running total in the log is the
 * cheapest way to notice a loop that should not be looping — the alternative is finding out
 * from the billing page.</p>
 *
 * <p><b>No retries.</b> On the query path a retry doubles the wait inside the turn budget;
 * on the sync path the row is marked {@code FAILED} and picked up next run, which is a
 * retry with a five-minute backoff and a spending cap attached.</p>
 */
@Component
public class UpstageEmbeddingClient implements EmbeddingClient {

    private static final Logger log = LoggerFactory.getLogger(UpstageEmbeddingClient.class);

    private final EmbeddingProperties properties;
    private final RestClient restClient;

    /** Billed calls made since boot. Logged so a runaway loop is visible in the log. */
    private final AtomicLong callCount = new AtomicLong();

    public UpstageEmbeddingClient(EmbeddingProperties properties) {
        this.properties = properties;

        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        Duration timeout = Duration.ofMillis(properties.getTimeoutMillis());
        factory.setConnectTimeout(timeout);
        factory.setReadTimeout(timeout);

        this.restClient = RestClient.builder()
            .baseUrl(properties.getBaseUrl())
            .requestFactory(factory)
            .build();
    }

    @PostConstruct
    void announce() {
        if (properties.isUsable()) {
            log.info("embedding ON: model={} dim={} (metered API — sync batch cap {}/run, "
                    + "sync job {})", properties.getPassageModel(), properties.getDimensions(),
                properties.getSyncBatchSize(),
                properties.isSyncEnabled() ? "enabled" : "disabled");
            return;
        }
        // ★ 조용히 넘어가지 않는다. 의미 검색이 꺼진 것은 지원되는 상태이지만 '의도한
        //   것'이어야 한다. 로그가 없으면 몇 주 뒤 "로봇이 옛날 얘기를 못 꺼낸다"는
        //   증상으로만 발견된다.
        log.warn("embedding OFF ({}): semantic search unavailable. Memory retrieval falls "
                + "back to keyword x importance x recency (S15P11E102-218)",
            properties.isEnabled() ? "no UPSTAGE_API_KEY" : "bomi.embedding.enabled=false");
    }

    @Override
    public boolean isAvailable() {
        return properties.isUsable();
    }

    @Override
    public String passageModelId() {
        return properties.getPassageModel();
    }

    @Override
    public int dimensions() {
        return properties.getDimensions();
    }

    @Override
    public float[] embedPassage(String text) {
        return embed(properties.getPassageModel(), text);
    }

    @Override
    public float[] embedQuery(String text) {
        return embed(properties.getQueryModel(), text);
    }

    private float[] embed(String model, String text) {
        if (!isAvailable()) {
            throw new EmbeddingFailedException("embedding is not configured");
        }
        if (text == null || text.isBlank()) {
            // 빈 문자열로도 과금된다. 비교 기준이 없는 턴(예: 스케줄 제안)에서 여기까지
            // 오는 경로가 있으면 매번 돈을 쓰고 아무것도 얻지 못한다.
            throw new EmbeddingFailedException("refusing to embed blank text");
        }

        long callNumber = callCount.incrementAndGet();
        try {
            EmbeddingResponse response = restClient.post()
                .uri("/embeddings")
                .header("Authorization", "Bearer " + properties.getApiKey())
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("model", model, "input", text))
                .retrieve()
                .body(EmbeddingResponse.class);

            float[] vector = firstVector(response, model);
            if (vector.length != properties.getDimensions()) {
                throw new EmbeddingFailedException(
                    "model %s returned %d dimensions but %d was configured; the vector store "
                        .formatted(model, vector.length, properties.getDimensions())
                        + "collections were created with the configured size and would reject "
                        + "this");
            }
            log.debug("embedded {} chars with {} (billed call #{})", text.length(), model,
                callNumber);
            return vector;
        } catch (EmbeddingFailedException error) {
            throw error;
        } catch (Exception error) {
            throw new EmbeddingFailedException(
                "embedding call #%d to %s failed".formatted(callNumber, model), error);
        }
    }

    private float[] firstVector(EmbeddingResponse response, String model) {
        if (response == null || response.data() == null || response.data().isEmpty()) {
            throw new EmbeddingFailedException("model " + model + " returned no embedding");
        }
        List<Double> values = response.data().get(0).embedding();
        if (values == null || values.isEmpty()) {
            throw new EmbeddingFailedException("model " + model + " returned an empty vector");
        }
        float[] vector = new float[values.size()];
        for (int i = 0; i < values.size(); i++) {
            vector[i] = values.get(i).floatValue();
        }
        return vector;
    }

    /** How many billed calls this process has made. Read by tests and by the sync job's log. */
    public long billedCallCount() {
        return callCount.get();
    }

    /**
     * OpenAI-compatible embedding response. Only the fields we use are declared.
     *
     * <p>{@code Double} rather than {@code Float} because Jackson maps JSON numbers to
     * {@code Double} by default; taking them as {@code Float} works but silently rounds
     * twice.</p>
     */
    private record EmbeddingResponse(List<Item> data) {
        private record Item(List<Double> embedding) {}
    }
}
