package com.ssafy.bomi.vector.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Qdrant connection settings (S15P11E102-218).
 *
 * <p>{@code host} blank means "no vector store". That is a supported state, not a
 * misconfiguration: a developer laptop without the container still has to boot, and the
 * assembly falls back to keyword × importance × recency ranking. It is announced at startup
 * rather than discovered later from a quiet drop in answer quality.</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.qdrant")
public class QdrantProperties {

    /** Hostname. Blank disables the vector store entirely. */
    private String host = "";

    /**
     * gRPC port, not the REST port (6333).
     *
     * <p>The official Java client speaks gRPC. Pointing this at 6333 fails with a protocol
     * error that reads like a network problem, which is a slow hour to debug.</p>
     */
    private int grpcPort = 6334;

    /** Blank means the server has no API key configured. */
    private String apiKey = "";

    /**
     * TLS. False is correct on {@code backend-net}, which is an internal docker network.
     *
     * <p>If Qdrant is ever moved off that network this must become true — the payload
     * carries senior ids and the vectors are derived from what the senior said.</p>
     */
    private boolean useTls = false;

    /**
     * Vector dimension. Must match the embedding model exactly.
     *
     * <p>4096 is Upstage {@code solar-embedding-1-large}. This is the number that made
     * pgvector impossible (its index ceiling is 2,000 / 4,000), so it is the reason this
     * whole package exists. Changing the model without changing this produces a dimension
     * error on every upsert.</p>
     */
    private int dimensions = 4096;

    /**
     * How long a single call may take.
     *
     * <p>Search sits inside the turn budget (about 2 seconds end to end, CLAUDE.md §18).
     * Waiting longer than this is worse than answering with shallower ranking, because the
     * senior is sitting in silence while we wait.</p>
     */
    private long timeoutMillis = 1_500;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host == null ? "" : host.trim();
    }

    public int getGrpcPort() {
        return grpcPort;
    }

    public void setGrpcPort(int grpcPort) {
        this.grpcPort = grpcPort;
    }

    public String getApiKey() {
        return apiKey;
    }

    public void setApiKey(String apiKey) {
        this.apiKey = apiKey == null ? "" : apiKey.trim();
    }

    public boolean isUseTls() {
        return useTls;
    }

    public void setUseTls(boolean useTls) {
        this.useTls = useTls;
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

    /** Whether a host was configured at all. */
    public boolean isConfigured() {
        return !host.isBlank();
    }
}
