package com.ssafy.bomi.conversation.application;

import com.ssafy.bomi.llm.config.LlmProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 대화 요약 생성을 주기적으로 돌린다 (S15P11E102-254).
 *
 * <p>{@code EmbeddingSyncScheduler} 와 같은 이유로 <b>빈 자체가</b> 조건부다:
 * {@code bomi.llm.enabled=false} (기본값) 이면 이 빈은 아예 존재하지 않는다 — 요금이
 * 드는 기능은 "만들어졌지만 매 틱 스스로 skip 한다"가 아니라 "꺼져 있으면 틱 자체가
 * 없다"여야, 로그를 안 보고도 과금 여부를 확신할 수 있다.</p>
 *
 * <p>{@code @EnableScheduling} 은 앱 전체에 이미 켜져 있다
 * ({@code com.ssafy.bomi.config.SchedulingConfig}) — 여기서는 {@code @Scheduled}
 * 메서드만 얹는다.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.llm", name = "enabled", havingValue = "true")
public class ConversationSummaryScheduler {

    private static final Logger log = LoggerFactory.getLogger(ConversationSummaryScheduler.class);

    private final ConversationSummaryService summaryService;
    private final DailyConversationSummaryService dailySummaryService;
    private final LlmProperties properties;

    public ConversationSummaryScheduler(
        ConversationSummaryService summaryService,
        DailyConversationSummaryService dailySummaryService,
        LlmProperties properties) {
        this.summaryService = summaryService;
        this.dailySummaryService = dailySummaryService;
        this.properties = properties;
    }

    @Scheduled(fixedDelayString = "${bomi.llm.sweep-interval-millis:300000}",
        initialDelayString = "${bomi.llm.sweep-interval-millis:300000}")
    public void run() {
        try {
            summaryService.summarizeDue();
        } catch (RuntimeException error) {
            // 스케줄러에서 예외가 새어 나가면 이 작업 자체가 조용히 제거된다 — 그러면
            // "로봇이 지난 대화를 기억 못 한다"는 증상만 몇 주 뒤에 발견된다.
            log.error("conversation summary sweep failed; will retry next tick "
                + "(cap {} calls/run)", properties.getMaxCallsPerRun(), error);
        }
    }

    /**
     * 매시 :20 분에 깨어나, 로컬 시각이 일간 요약 창에 들어온 어르신의 전날을 요약한다
     * (S15P11E102 G1).
     *
     * <p><b>왜 새벽 cron 하나가 아니라 매시간인가.</b> 컨테이너 시계는 UTC 이고 어르신마다
     * {@code time_zone} 이 다르다. UTC 고정 cron 은 정확히 한 시간대의 어르신만 새벽
     * 2시에 맞고 나머지는 한낮에 요약된다. 그 오차는 예외 하나 없이 "요약 기간이 하루
     * 밀린 채 그럴듯하게" 나타난다 — 창 판정은 어르신의 로컬 시각으로만 할 수 있고,
     * 그러려면 매시간 깨어나야 한다.</p>
     *
     * <p><b>왜 정시가 아니라 :20 분인가.</b> 스프링 기본 스케줄러 풀은 스레드 1개다
     * ({@code SchedulingConfig}). 정시에 몰린 다른 틱(대화 요약 스윕·복약·워치독)과
     * 겹치면 이 틱이 통째로 밀리고, 밀린 cron 틱은 큐에 쌓이지 않고 <b>버려진다</b>.</p>
     *
     * <p><b>{@code @Transactional} 을 붙이면 안 된다.</b> 붙이는 순간 초 단위 LLM 호출이
     * 트랜잭션 안으로 들어가 Hikari 커넥션을 그만큼 붙잡는다
     * ({@link DailyConversationSummaryService} 자바독 참고). {@code MedicationReminderScheduler}
     * 와 다른 점이 바로 여기다.</p>
     *
     * <p>이 메서드를 별도 스케줄러 클래스로 빼지 않은 이유 — 이 빈의
     * {@code @ConditionalOnProperty(bomi.llm.enabled)} 게이트가 일간 요약에도 글자 그대로
     * 동일하고, 같은 {@link LlmProperties} 예산을 나눠 쓴다. 조건이 같은 두 번째 조건부
     * 빈은 순수한 중복이다.</p>
     */
    @Scheduled(cron = "${bomi.llm.daily-summary-cron:0 20 * * * *}")
    public void runDaily() {
        try {
            dailySummaryService.summarizeDueDays();
        } catch (RuntimeException error) {
            log.error("daily conversation summary sweep failed; the next hourly tick retries "
                + "(cap {} calls/run)", properties.getMaxCallsPerRun(), error);
        }
    }
}
