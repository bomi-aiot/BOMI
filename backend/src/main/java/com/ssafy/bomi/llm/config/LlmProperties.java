package com.ssafy.bomi.llm.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Generative LLM client settings (prefix {@code bomi.llm}, S15P11E102-254).
 *
 * <p><b>Off by default, and that is deliberate.</b> Same reasoning as
 * {@code EmbeddingProperties}: this is the second (and, for now, last) metered external API
 * the backend calls, and the project runs on a small prepaid balance that also has to cover
 * the prototype demo. A default of "on" means every test run, every local boot, and every CI
 * job that happens to have a key in its environment spends money.</p>
 *
 * <p><b>Reused for whatever generation consumer comes next.</b> Today the only caller is
 * {@code ConversationSummaryService}. Nothing here is summary-specific — {@link #maxCallsPerRun}
 * and {@link #sweepIntervalMillis} describe "a scheduled job that calls {@code generate()}
 * repeatedly", not "the summary job" by name — so a later generation consumer can share this
 * class instead of inventing its own on/off switch and spending cap.</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.llm")
public class LlmProperties {

    /** Master switch. False means no calls are made at all, whatever else is set. */
    private boolean enabled = false;

    /** Blank disables generation even when {@link #enabled} is true. */
    private String apiKey = "";

    /**
     * GMS(SSAFY 사내 게이트웨이)를 경유한 Gemini 엔드포인트 베이스.
     *
     * <p>로봇 쪽 {@code llm/client.py} 가 이미 같은 경로를 쓰고 있다 — 두 채널이 같은
     * 게이트웨이 뒤에서 같은 계정으로 과금된다는 뜻이다. 값을 바꿀 때는 로봇 쪽도
     * 함께 확인해야 한다(서로 다른 워크트리라 자동으로 맞춰지지 않는다).</p>
     */
    private String baseUrl = "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com";

    private String model = "gemini-2.5-flash-lite";

    /**
     * Per-call timeout.
     *
     * <p>Unlike {@code EmbeddingProperties.timeoutMillis} this is <b>not</b> inside the
     * ~2s turn budget (CLAUDE.md §18) — every caller of this client runs off a scheduled
     * sweep, never on a senior's turn. The number is generous because a summary is worth
     * waiting a few extra seconds for; it still has a ceiling because a hung call must not
     * pin a sweep thread forever.</p>
     */
    private long timeoutMillis = 8_000;

    /** Upper bound on the model's response length, passed as {@code generationConfig}. */
    private int maxOutputTokens = 220;

    /**
     * How many generate() calls one scheduled run may make.
     *
     * <p><b>This is a spending cap, not a tuning knob</b> — the same rule
     * {@code EmbeddingProperties.syncBatchSize} documents. Each call is billed. With this
     * cap and a five-minute sweep interval, the worst case is bounded and visible in the
     * log; without it, a backlog of closed conversations (say, after downtime) would
     * summarise in one uncontrolled burst.</p>
     */
    private int maxCallsPerRun = 20;

    /**
     * How many of a conversation's most recent messages go into one summary prompt.
     *
     * <p>Deliberately larger than {@code ContextAssemblyProperties.recentMessageMax} (12):
     * that limit exists to keep a live turn's prompt short enough to read aloud
     * (CLAUDE.md §14), and this one runs off the turn path entirely, summarising a whole
     * conversation after the fact. Still capped — an unbounded transcript would make both
     * the prompt size and the bill unpredictable.</p>
     */
    private int maxSummaryMessages = 60;

    /** Milliseconds between summary sweep runs. Not urgent, so this can be generous. */
    private long sweepIntervalMillis = 300_000;

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

    public String getModel() {
        return model;
    }

    public void setModel(String model) {
        this.model = model;
    }

    public long getTimeoutMillis() {
        return timeoutMillis;
    }

    public void setTimeoutMillis(long timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }

    public int getMaxOutputTokens() {
        return maxOutputTokens;
    }

    public void setMaxOutputTokens(int maxOutputTokens) {
        this.maxOutputTokens = maxOutputTokens;
    }

    public int getMaxCallsPerRun() {
        return maxCallsPerRun;
    }

    public void setMaxCallsPerRun(int maxCallsPerRun) {
        this.maxCallsPerRun = maxCallsPerRun;
    }

    public int getMaxSummaryMessages() {
        return maxSummaryMessages;
    }

    public void setMaxSummaryMessages(int maxSummaryMessages) {
        this.maxSummaryMessages = maxSummaryMessages;
    }

    public long getSweepIntervalMillis() {
        return sweepIntervalMillis;
    }

    public void setSweepIntervalMillis(long sweepIntervalMillis) {
        this.sweepIntervalMillis = sweepIntervalMillis;
    }

    /** Whether calls may actually be made. */
    public boolean isUsable() {
        return enabled && !apiKey.isBlank();
    }
}
