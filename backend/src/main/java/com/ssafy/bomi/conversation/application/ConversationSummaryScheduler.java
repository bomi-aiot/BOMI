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
    private final LlmProperties properties;

    public ConversationSummaryScheduler(
        ConversationSummaryService summaryService, LlmProperties properties) {
        this.summaryService = summaryService;
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
}
