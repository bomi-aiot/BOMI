package com.ssafy.bomi.embedding.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Embedding model settings (S15P11E102-218).
 *
 * <p><b>Off by default, and that is deliberate.</b> This is the only metered external API in
 * the backend, and the project runs on a small prepaid balance that also has to cover the
 * prototype demo. A default of "on" means every test run, every local boot, and every CI
 * job that happens to have a key in its environment spends money. Turning it on is one line
 * in the deployment env; getting a drained balance back is not.</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.embedding")
public class EmbeddingProperties {

    /** Master switch. False means no calls are made at all, whatever else is set. */
    private boolean enabled = false;

    /** Blank disables embedding even when {@link #enabled} is true. */
    private String apiKey = "";

    private String baseUrl = "https://api.upstage.ai/v1";

    /**
     * Model for stored text.
     *
     * <p>Must stay paired with {@link #queryModel} — see {@code EmbeddingClient} for why
     * mixing the two degrades search silently.</p>
     */
    private String passageModel = "embedding-passage";

    /** Model for search text. */
    private String queryModel = "embedding-query";

    /** 4096 for solar-embedding-1-large. The number pgvector could not index. */
    private int dimensions = 4096;

    /**
     * Per-call timeout.
     *
     * <p>{@code embedQuery} runs inside the turn budget (~2s, CLAUDE.md §18). Answering with
     * shallower ranking beats making the senior wait longer.</p>
     */
    private long timeoutMillis = 1_200;

    /**
     * How many rows one sync run may embed.
     *
     * <p><b>This is a spending cap, not a tuning knob.</b> Each row is one billed call. With
     * a 30-row cap and a 5-minute interval the worst case is bounded and visible; without a
     * cap, one full reindex of a long-running household is a single unbounded burst.</p>
     */
    private int syncBatchSize = 30;

    /**
     * Whether the periodic sync job runs.
     *
     * <p>Separate from {@link #enabled} on purpose. During the demo we want
     * {@code embedQuery} working (one small call per utterance) without a background job
     * quietly working through a backlog at the same time.</p>
     */
    private boolean syncEnabled = false;

    /** Milliseconds between sync runs. Long, because nothing here is urgent. */
    private long syncIntervalMillis = 300_000;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey == null ? "" : apiKey.trim();
    }

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String getPassageModel() {
        return passageModel;
    }

    public void setPassageModel(String passageModel) {
        this.passageModel = passageModel;
    }

    public String getQueryModel() {
        return queryModel;
    }

    public void setQueryModel(String queryModel) {
        this.queryModel = queryModel;
    }

    public int getDimensions() {
        return dimensions;
    }

    public void setDimensions(int dimensions) {
        this.dimensions = dimensions;
    }

    public long getTimeoutMillis() {
        return timeoutMillis;
    }

    public void setTimeoutMillis(long timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }

    public int getSyncBatchSize() {
        return syncBatchSize;
    }

    public void setSyncBatchSize(int syncBatchSize) {
        this.syncBatchSize = syncBatchSize;
    }

    public boolean isSyncEnabled() {
        return syncEnabled;
    }

    public void setSyncEnabled(boolean syncEnabled) {
        this.syncEnabled = syncEnabled;
    }

    public long getSyncIntervalMillis() {
        return syncIntervalMillis;
    }

    public void setSyncIntervalMillis(long syncIntervalMillis) {
        this.syncIntervalMillis = syncIntervalMillis;
    }

    /** Whether calls may actually be made. */
    public boolean isUsable() {
        return enabled && !apiKey.isBlank();
    }
}
