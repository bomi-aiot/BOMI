package com.ssafy.bomi.conversation.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * A conversation between a senior and the robot (maps table {@code conversation}).
 *
 * <p>Aggregate root of the raw-utterance boundary. It holds no utterance body;
 * {@code started_at} is the start, {@code ended_at} covers normal/failed/cancelled
 * termination, and {@code raw_messages_expires_at} is the earliest time raw
 * messages may be deleted (§4). {@code senior_id} references {@code app_user} and
 * {@code scenario_id} optionally references {@code scenario}; both are raw
 * {@link UUID} logical references.</p>
 */
@Entity
@Table(name = "conversation")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Conversation {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "scenario_id")
    private UUID scenarioId;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 30)
    private ConversationStatus status = ConversationStatus.OPEN;

    @Column(name = "started_at")
    private OffsetDateTime startedAt;

    @Column(name = "ended_at")
    private OffsetDateTime endedAt;

    @Column(name = "raw_messages_expires_at")
    private OffsetDateTime rawMessagesExpiresAt;

    /**
     * 이 대화가 "우리끼리 얘기" 류 표현으로 봉인됐는가 (S15P11E102-254, V12).
     *
     * <p>로봇(ai_chat) 이 로컬에서 판정하고, {@code POST .../end} 로 대화를 닫을 때
     * 함께 실어 보낸다(S15P11E102-253 {@code emotion.is_conversation_sealed}). 봉인된
     * 대화는 요약 생성 대상에서 제외한다 — 원문을 외부 생성형 LLM(Gemini) 에 보내는
     * 것 자체가 "우리끼리 얘기"라는 약속을 깨기 때문이다(CLAUDE.md §9 T4).</p>
     *
     * <p>기본값 false. 로봇 쪽 봉인 판정 로직이 아직 이 값을 채워 보내는 경로를
     * 갖추지 않았다면(별도 AI 라인 작업), 모든 대화가 봉인되지 않은 것으로 취급된다 —
     * 안전한 방향의 기본값은 아니지만(과다 요약 쪽으로 실패), 로봇이 실제로 이 필드를
     * 채워 보내기 전까지는 백엔드 혼자서 봉인 여부를 알 방법이 없다.</p>
     */
    @Column(name = "sealed", nullable = false)
    private boolean sealed = false;

    private Conversation(UUID seniorId, UUID scenarioId) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.scenarioId = scenarioId;
        this.startedAt = OffsetDateTime.now();
    }

    public static Conversation open(UUID seniorId) {
        return new Conversation(seniorId, null);
    }

    public static Conversation openForScenario(UUID seniorId, UUID scenarioId) {
        return new Conversation(seniorId, scenarioId);
    }

    /** Marks the conversation ended with a terminal status (COMPLETED/FAILED/CANCELLED). */
    public void end(ConversationStatus terminalStatus) {
        if (terminalStatus == null || terminalStatus == ConversationStatus.OPEN) {
            throw new IllegalArgumentException("terminalStatus must be a terminal status");
        }
        this.status = terminalStatus;
        this.endedAt = OffsetDateTime.now();
    }

    public void scheduleRawExpiry(OffsetDateTime expiresAt) {
        this.rawMessagesExpiresAt = expiresAt;
    }

    /** 이 대화를 봉인한다. 되돌릴 수 없다 — 봉인은 한 방향의 약속이다. */
    public void markSealed() {
        this.sealed = true;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
