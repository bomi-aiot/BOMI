package com.ssafy.bomi.conversation.application;

import com.ssafy.bomi.conversation.config.ConversationLifecycleProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 유휴시간을 넘긴 OPEN 대화를 주기적으로 닫는다 (S15P11E102-254).
 *
 * <p>{@code @EnableScheduling} 은 이미 {@code com.ssafy.bomi.config.SchedulingConfig}
 * 가 앱 전체에 켜 두었다(복약 알림 시나리오 ② 때 처음 켰다) — 이 클래스는 그 위에
 * {@code @Scheduled} 메서드 하나만 얹는다. 새 스케줄링 인프라를 만들지 않는다.</p>
 *
 * <p>다른 스윕(예: {@code EmbeddingSyncScheduler})과 달리 기본값이 <b>켜짐</b>이다 —
 * 여기엔 과금되는 외부 호출이 없고, 꺼져 있으면 이 티켓이 고치는 바로 그 문제(대화가
 * 영원히 OPEN)로 되돌아가기 때문이다.</p>
 */
@Component
@ConditionalOnProperty(
    prefix = "bomi.conversation-lifecycle", name = "sweep-enabled",
    havingValue = "true", matchIfMissing = true)
public class ConversationLifecycleSweeper {

    private static final Logger log = LoggerFactory.getLogger(ConversationLifecycleSweeper.class);

    private final ConversationLifecycleService lifecycleService;

    public ConversationLifecycleSweeper(ConversationLifecycleService lifecycleService) {
        this.lifecycleService = lifecycleService;
    }

    @Scheduled(fixedDelayString = "${bomi.conversation-lifecycle.sweep-interval-millis:60000}",
        initialDelayString = "${bomi.conversation-lifecycle.sweep-interval-millis:60000}")
    public void sweep() {
        try {
            lifecycleService.closeIdleConversations();
        } catch (RuntimeException error) {
            // 스케줄러에서 예외가 새어 나가면 이 작업 자체가 조용히 제거된다. 그러면
            // 대화가 다시는 자동으로 안 닫히는데, 겉으로는 아무 문제도 안 보인다.
            log.error("conversation lifecycle sweep failed; will retry next tick", error);
        }
    }
}
