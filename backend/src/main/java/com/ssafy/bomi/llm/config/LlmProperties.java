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
 * <p><b>Reused for whatever generation consumer comes next.</b> The callers today are
 * {@code ConversationSummaryService} and {@code DailyConversationSummaryService}. Nothing here
 * is summary-specific — {@link #maxCallsPerRun} and {@link #sweepIntervalMillis} describe
 * "a scheduled job that calls {@code generate()} repeatedly", not "the summary job" by name —
 * so a later generation consumer can share this class instead of inventing its own on/off
 * switch and spending cap. {@link #maxCallsPerRun} is deliberately shared by both sweeps:
 * it is one budget, not one budget per job.</p>
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

    /**
     * 하루치 요약 프롬프트에 실을 발화 수 상한 (S15P11E102 G1).
     *
     * <p>{@link #maxSummaryMessages}(60) 를 재사용하지 않는 이유는 단위가 다르기
     * 때문이다 — 저건 대화 <em>하나</em>의 꼬리이고, 이건 하루에 있었던 <em>모든</em>
     * 대화의 꼬리다. 60 을 그대로 쓰면 말이 많았던 날의 앞부분이 통째로 잘려 나가는데,
     * 잘려 나갔다는 사실은 요약문 어디에도 드러나지 않는다.</p>
     *
     * <p>그래도 상한은 둔다. 하루 200발화면 대화 요약 프롬프트의 3배가 넘는 토큰이고,
     * 상한이 없으면 프롬프트 크기와 청구액이 둘 다 예측 불가능해진다.</p>
     */
    private int maxDailySummaryMessages = 200;

    /**
     * 일간 요약을 시작하는 <b>어르신 현지</b> 시각(시). ERD §4 의 "새벽 2~3시 배치".
     *
     * <p>컨테이너 시계(UTC)가 아니라 어르신의 시간대로 판정한다. UTC 고정 cron 은
     * 정확히 한 시간대의 어르신만 새벽에 맞고 나머지는 한낮에 요약되는데, 그 오차는
     * 예외 없이 "요약 기간이 하루 밀린 채 그럴듯하게" 나타난다.</p>
     */
    private int dailySummaryHour = 2;

    /**
     * 일간 요약 창의 길이(시간). 로컬 {@code [hour, hour + this)} 안의 매시간 틱이
     * 그날의 재시도가 된다.
     *
     * <p><b>1 이 아니라 4 가 기본인 이유.</b> 스프링 기본 스케줄러 풀은 스레드 1개다
     * ({@code SchedulingConfig}). 02:00 틱이 대화 요약 스윕(최대 20호출 × 8초)이나
     * 재배포에 밀리면 스프링 cron 은 놓친 실행을 큐에 쌓지 않고 <b>건너뛴다</b> —
     * 창이 한 시간이면 그날 요약은 다음 날이 아니라 <em>영영</em> 생기지 않는다(어제는
     * 이미 지나갔다). 재시도 비용은 "값싼 exists 쿼리 한 번"뿐이다.</p>
     *
     * <p>창은 자정을 넘지 않는다({@code hour + this} 는 24 로 잘린다). 자정을 넘기면
     * 창의 앞뒤에서 "어제"가 서로 다른 날짜를 가리켜 하루가 두 번 요약된다.</p>
     */
    private int dailySummaryWindowHours = 4;

    /**
     * 일간 요약 틱의 cron. 기본값은 매시 :20 분.
     *
     * <p>정시가 아닌 이유 — 같은 단일 스레드를 쓰는 다른 틱(대화 요약 스윕·복약·워치독)이
     * 정시에 몰린다. 거기에 겹치면 이 틱이 통째로 밀리고, 밀린 틱은 재실행되지 않는다.</p>
     */
    private String dailySummaryCron = "0 20 * * * *";

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

    public int getMaxDailySummaryMessages() {
        return maxDailySummaryMessages;
    }

    public void setMaxDailySummaryMessages(int maxDailySummaryMessages) {
        this.maxDailySummaryMessages = maxDailySummaryMessages;
    }

    public int getDailySummaryHour() {
        return dailySummaryHour;
    }

    public void setDailySummaryHour(int dailySummaryHour) {
        this.dailySummaryHour = dailySummaryHour;
    }

    public int getDailySummaryWindowHours() {
        return dailySummaryWindowHours;
    }

    public void setDailySummaryWindowHours(int dailySummaryWindowHours) {
        this.dailySummaryWindowHours = dailySummaryWindowHours;
    }

    public String getDailySummaryCron() {
        return dailySummaryCron;
    }

    public void setDailySummaryCron(String dailySummaryCron) {
        this.dailySummaryCron = dailySummaryCron;
    }

    /** Whether calls may actually be made. */
    public boolean isUsable() {
        return enabled && !apiKey.isBlank();
    }
}
