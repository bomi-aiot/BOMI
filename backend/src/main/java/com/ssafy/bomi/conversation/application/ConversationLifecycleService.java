package com.ssafy.bomi.conversation.application;

import com.ssafy.bomi.conversation.config.ConversationLifecycleProperties;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 대화의 시작과 끝을 판단한다 — 서버가 "이게 하나의 대화다"를 결정하는 유일한 자리
 * (S15P11E102-254).
 *
 * <p>어디에 위치하는가
 *     {@code RobotConversationService.record} 가 매 턴마다 이 서비스에게 "이 발화가
 *     어느 대화에 속하는가"를 묻는다. {@code RobotConversationController} 의
 *     {@code POST .../end} 는 로봇이 이미 내린 "이 대화는 끝났다" 판단을 서버에
 *     반영한다. {@code ConversationLifecycleSweeper} 는 다음 발화가 영영 오지 않는
 *     경우(로봇이 재시작했거나, 어르신이 그냥 대화를 멈춘 경우)를 위한 안전망이다.</p>
 *
 * <p>왜 존재하는가
 *     이 서비스가 생기기 전에는 {@code RobotConversationService.resolveConversation}
 *     이 매번 {@code Conversation.open(...)} 을 부르거나 넘어온 id 를 그대로 썼다 —
 *     대화가 절대 안 닫히고, 발화 하나하나가 사실상 자기만의 대화였다. 그 결과
 *     {@code conversation_summary} 를 채울 재료(닫힌 대화)가 아예 생기지 않았다.</p>
 */
@Service
public class ConversationLifecycleService {

    private static final Logger log = LoggerFactory.getLogger(ConversationLifecycleService.class);

    private final ConversationRepository conversationRepository;
    private final ConversationMessageRepository messageRepository;
    private final ConversationLifecycleProperties properties;
    private final Clock clock;

    public ConversationLifecycleService(
        ConversationRepository conversationRepository,
        ConversationMessageRepository messageRepository,
        ConversationLifecycleProperties properties,
        Clock clock
    ) {
        this.conversationRepository = conversationRepository;
        this.messageRepository = messageRepository;
        this.properties = properties;
        this.clock = clock;
    }

    /**
     * 새 발화가 이어갈 대화의 id 를 정한다. 필요하면 이전 대화를 닫고 새로 연다.
     *
     * <p>무엇을 하는가</p>
     * <ul>
     *   <li>{@code conversationId} 가 없으면 새로 연다.</li>
     *   <li>넘어온 id 가 존재하지 않으면 예외를 던진다(잘못된 id 를 조용히 새 대화로
     *       치환하면, 로봇이 자신의 id 가 틀렸다는 것을 영영 모른다).</li>
     *   <li>존재하지만 이미 닫혀 있으면(다른 경로가 먼저 닫았거나, 스윕이 먼저
     *       닫았거나) 예외 대신 <b>새 대화를 조용히 연다</b> — 완료 조건이 명시한
     *       복구 동작이다.</li>
     *   <li>OPEN 이고 마지막 활동으로부터 {@code idleTimeout} 을 넘겼으면 지금
     *       닫고 새로 연다.</li>
     *   <li>그 외에는 그대로 이어간다.</li>
     * </ul>
     *
     * @param occurredAt 이 발화가 실제로 일어난 시각(로봇의 시계). 유휴시간 판정의
     *     "지금"으로 쓴다 — 서버 도착 시각이 아니다(CLAUDE.md §15 의 정신을 백엔드
     *     쪽에서도 지킨다: 비교 기준은 항상 호출자가 준 시각이다).
     */
    @Transactional
    public UUID openOrContinue(UUID seniorId, UUID conversationId, OffsetDateTime occurredAt) {
        if (conversationId == null) {
            return open(seniorId);
        }

        Conversation existing = conversationRepository.findById(conversationId)
            .orElseThrow(() -> new IllegalArgumentException(
                "unknown conversationId: " + conversationId));
        if (!existing.getSeniorId().equals(seniorId)) {
            // 한 어르신의 발화를 다른 어르신의 대화에 붙이면 그 사람의 프롬프트
            // 문맥으로 새어 들어간다. 조용한 최선 추측이 아니라 loud failure.
            throw new IllegalArgumentException(
                "conversation " + conversationId + " does not belong to senior " + seniorId);
        }

        if (existing.getStatus() != ConversationStatus.OPEN) {
            log.info("conversation {} was already closed ({}); opening a new one for the "
                + "incoming turn", conversationId, existing.getStatus());
            return open(seniorId);
        }

        OffsetDateTime lastActivity = lastActivityOf(existing);
        if (lastActivity != null && isIdle(lastActivity, occurredAt)) {
            closeForIdle(existing, occurredAt);
            return open(seniorId);
        }

        return existing.getId();
    }

    /**
     * 로봇이 이미 내린 "이 대화는 끝났다"는 판단을 반영한다.
     *
     * <p>{@code status} 가 종료 상태(COMPLETED/FAILED/CANCELLED)가 아니면 거부한다 —
     * OPEN 으로 "끝낸다"는 요청은 호출부의 버그다.</p>
     *
     * <p>이미 닫힌 대화에 다시 오면 조용히 현재 상태를 그대로 돌려준다. 로봇의
     * 아웃박스가 재시도로 같은 종료를 두 번 보낼 수 있는데, 두 번째 호출이 첫 번째
     * 판정(예: FAILED — 무응답 probe)을 재시도의 값(예: COMPLETED)으로 덮어쓰면
     * "왜 새벽 3시에 실패했나"를 되짚을 근거가 사라진다.</p>
     *
     * @param sealed {@code true} 면 이 대화를 봉인한다(§9 T4). {@code null}/{@code false}
     *     는 아무것도 하지 않는다 — 봉인은 한 방향이라 "봉인 해제"라는 개념이 없다.
     */
    @Transactional
    public Conversation end(UUID conversationId, UUID seniorId, ConversationStatus status,
        Boolean sealed) {

        if (status == null || status == ConversationStatus.OPEN) {
            throw new IllegalArgumentException(
                "status must be a terminal status (COMPLETED, FAILED, or CANCELLED)");
        }

        Conversation conversation = conversationRepository.findById(conversationId)
            .orElseThrow(() -> new IllegalArgumentException(
                "unknown conversationId: " + conversationId));
        if (!conversation.getSeniorId().equals(seniorId)) {
            throw new IllegalArgumentException(
                "conversation " + conversationId + " does not belong to senior " + seniorId);
        }

        if (Boolean.TRUE.equals(sealed)) {
            conversation.markSealed();
        }

        if (conversation.getStatus() != ConversationStatus.OPEN) {
            log.info("conversation {} end() called again (already {}); ignoring the new "
                + "status to avoid overwriting the first terminal reason", conversationId,
                conversation.getStatus());
            return conversationRepository.save(conversation);
        }

        conversation.end(status);
        conversation.scheduleRawExpiry(
            conversation.getEndedAt().plusDays(properties.getRawRetentionDays()));
        return conversationRepository.save(conversation);
    }

    /**
     * 유휴시간을 넘긴 OPEN 대화를 전부 닫는다. {@code ConversationLifecycleSweeper} 가
     * 주기적으로 호출하는 안전망이다 — 다음 발화가 영영 오지 않으면
     * {@link #openOrContinue} 는 절대 실행될 기회가 없기 때문에 이 스윕이 필요하다.
     *
     * @return 이번 실행에서 닫은 대화 수
     */
    @Transactional
    public int closeIdleConversations() {
        OffsetDateTime now = OffsetDateTime.now(clock);
        List<Conversation> open = conversationRepository.findByStatus(ConversationStatus.OPEN);
        int closed = 0;
        for (Conversation conversation : open) {
            OffsetDateTime lastActivity = lastActivityOf(conversation);
            if (lastActivity != null && isIdle(lastActivity, now)) {
                closeForIdle(conversation, now);
                closed++;
            }
        }
        if (closed > 0) {
            log.info("conversation lifecycle sweep closed {} idle conversation(s)", closed);
        }
        return closed;
    }

    private UUID open(UUID seniorId) {
        return conversationRepository.save(Conversation.open(seniorId)).getId();
    }

    /**
     * 발화가 하나라도 있으면 COMPLETED, 하나도 없으면 CANCELLED 로 닫는다 — 완료
     * 조건이 명시적으로 요구하는 구분이다.
     */
    private void closeForIdle(Conversation conversation, OffsetDateTime now) {
        boolean hasMessages = messageRepository.existsByConversationId(conversation.getId());
        ConversationStatus terminal =
            hasMessages ? ConversationStatus.COMPLETED : ConversationStatus.CANCELLED;
        conversation.end(terminal);
        conversation.scheduleRawExpiry(now.plusDays(properties.getRawRetentionDays()));
        conversationRepository.save(conversation);
    }

    /** 발화가 있으면 그 마지막 시각, 없으면 대화 시작 시각. */
    private OffsetDateTime lastActivityOf(Conversation conversation) {
        OffsetDateTime lastMessageAt = messageRepository.findMaxOccurredAt(conversation.getId());
        return lastMessageAt != null ? lastMessageAt : conversation.getStartedAt();
    }

    private boolean isIdle(OffsetDateTime lastActivity, OffsetDateTime now) {
        return Duration.between(lastActivity, now).compareTo(properties.getIdleTimeout()) > 0;
    }
}
