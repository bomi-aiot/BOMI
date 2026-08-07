package com.ssafy.bomi.conversation.application;

import com.ssafy.bomi.conversation.config.ConversationLifecycleProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 보존기간이 지난 원본 발화 삭제 잡의 타이머 (ERD §4, 검증 시나리오 31·32).
 *
 * <p><b>★ 빈 자체가 조건부다.</b> {@code bomi.conversation-lifecycle.purge-enabled} 가
 * 명시적으로 {@code true} 일 때만 이 클래스가 존재한다. 같은 패키지의
 * {@code ConversationLifecycleSweeper} 는 {@code matchIfMissing = true} 로 정반대인데,
 * 그것은 저쪽이 "꺼지면 문제가 되돌아오는" 무해한 잡이기 때문이다. 이쪽은 되돌릴 수
 * 없는 삭제라 기준이 다르다 — {@code EmbeddingSyncScheduler} 가 세운 기준을 그대로
 * 따른다: 위험한 기능은 "만들어졌지만 매 틱 스스로 skip 한다"가 아니라 <b>"꺼져 있으면
 * 틱 자체가 없다"</b> 여야 로그를 안 보고도 확신할 수 있다. 저기는 돈이 걸려 있었고,
 * 여기는 어르신의 대화다.</p>
 *
 * <p><b>왜 존재하는가.</b> 이 타이머가 없으면 {@code ConversationRawPurgeService} 를
 * 부르는 것이 아무것도 없어, 발화는 보존기간이 지나도 영원히 남는다 — 이 작업 이전의
 * 상태로 정확히 되돌아간다.</p>
 *
 * <p>{@code @EnableScheduling} 은 {@code com.ssafy.bomi.config.SchedulingConfig} 가 이미
 * 앱 전체에 켜 두었다. 여기서 새 스케줄링 인프라를 만들지 않는다.</p>
 */
@Component
@ConditionalOnProperty(
    prefix = "bomi.conversation-lifecycle", name = "purge-enabled", havingValue = "true")
public class ConversationRawPurgeSweeper {

    private static final Logger log = LoggerFactory.getLogger(ConversationRawPurgeSweeper.class);

    private final ConversationRawPurgeService purgeService;
    private final ConversationLifecycleProperties properties;

    public ConversationRawPurgeSweeper(ConversationRawPurgeService purgeService,
        ConversationLifecycleProperties properties) {
        this.purgeService = purgeService;
        this.properties = properties;
    }

    /**
     * "이 배포는 발화를 지운다"를 기동 시 1회 알린다.
     *
     * <p><b>{@code INFO} 가 아니라 {@code WARN} 인 이유:</b> 이 한 줄이 유일한 사전
     * 경고다. 삭제는 조용하고, 되돌릴 수 없고, 지워진 뒤에는 무엇이 있었는지조차 알 수
     * 없다. 운영자가 로그를 훑을 때 눈에 걸려야 한다.</p>
     *
     * <p>{@code ApplicationReadyEvent} 를 쓰는 이유는 {@code EmbeddingSyncScheduler} 의
     * 선례와 같다 — 빈 생성 시점에 부작용을 두지 않는다.</p>
     */
    @EventListener(ApplicationReadyEvent.class)
    public void announce() {
        log.warn("conversation raw purge is ENABLED: utterances of a conversation are "
            + "permanently deleted {} day(s) after it closes, at most {} conversation(s) per "
            + "run, every {}ms. There is no undo and no backup of conversation_message.",
            properties.getRawRetentionDays(), properties.getPurgeBatchSize(),
            properties.getPurgeIntervalMillis());
    }

    /**
     * {@code initialDelayString} 을 주기와 같게 둔다 — 기동 직후 즉시 삭제가 돌면 잘못
     * 켠 것을 알아채고 끌 시간이 없다. 기본 1시간이면 부팅 경고를 보고 되돌릴 수 있다.
     *
     * <p>{@code fixedDelay} 인 이유는 {@code EmbeddingSyncScheduler} 와 같다:
     * {@code fixedRate} 는 이전 실행의 <em>시작</em>부터 세어 긴 실행이 다음 실행과
     * 겹치는데, 겹친 두 실행은 같은 대화를 함께 잡는다.</p>
     */
    @Scheduled(
        fixedDelayString = "${bomi.conversation-lifecycle.purge-interval-millis:3600000}",
        initialDelayString = "${bomi.conversation-lifecycle.purge-interval-millis:3600000}")
    public void run() {
        try {
            purgeService.purgeExpired();
        } catch (RuntimeException error) {
            // 스케줄러 밖으로 예외가 나가면 그 작업이 조용히 제거된다. 삭제가 멈춘 것은
            // 즉시 드러나지 않으므로(아무것도 안 지워지는 것은 겉보기에 정상이다)
            // 반드시 로그로 남기고 다음 틱에 다시 시도한다. 기존 두 스위퍼와 같은 판단.
            log.error("conversation raw purge failed; will retry next tick", error);
        }
    }
}
