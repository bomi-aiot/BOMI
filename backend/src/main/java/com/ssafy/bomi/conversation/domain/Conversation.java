package com.ssafy.bomi.conversation.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
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
@Table(
    name = "conversation",
    uniqueConstraints = {
        @UniqueConstraint(name = "uq_conversation_scenario", columnNames = "scenario_id"),
        @UniqueConstraint(name = "uq_conversation_start_command", columnNames = "start_command_id")
    }
)
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

    /** START_CONVERSATION command correlated by CONVERSATION_STARTED. */
    @Column(name = "start_command_id", length = 64)
    private String startCommandId;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 30)
    private ConversationStatus status = ConversationStatus.OPEN;

    @Column(name = "started_at")
    private OffsetDateTime startedAt;

    /** Time at which AI confirmed it was ready, separate from the request time. */
    @Column(name = "ai_started_at")
    private OffsetDateTime aiStartedAt;

    @Column(name = "ended_at")
    private OffsetDateTime endedAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "end_outcome", length = 30)
    private ConversationOutcome endOutcome;

    @Column(name = "reason_code", length = 100)
    private String reasonCode;

    @Column(name = "raw_messages_expires_at")
    private OffsetDateTime rawMessagesExpiresAt;

    /**
     * 이 대화가 "우리끼리 얘기" 류 표현으로 봉인됐는가 (S15P11E102-254, V12).
     *
     * <p>로봇(ai_chat)이 로컬에서 판정하고,
     * {@code POST .../end}로 대화를 닫을 때 함께 전달한다.
     * 봉인된 대화는 요약 생성 대상에서 제외한다.</p>
     *
     * <p>기본값은 false이다. 봉인은 한 번 적용되면 되돌리지 않는다.</p>
     */
    @Column(name = "sealed", nullable = false)
    private boolean sealed = false;

    private Conversation(
        UUID seniorId,
        UUID scenarioId,
        OffsetDateTime requestedAt
    ) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.scenarioId = scenarioId;
        this.startedAt = requireNonNull(requestedAt, "requestedAt");
    }

    public static Conversation open(UUID seniorId) {
        OffsetDateTime now = OffsetDateTime.now();

        Conversation conversation = new Conversation(
            seniorId,
            null,
            now
        );

        conversation.aiStartedAt = now;
        return conversation;
    }

    public static Conversation openForScenario(
        UUID seniorId,
        UUID scenarioId
    ) {
        OffsetDateTime now = OffsetDateTime.now();

        Conversation conversation = new Conversation(
            seniorId,
            scenarioId,
            now
        );

        conversation.aiStartedAt = now;
        return conversation;
    }

    /** Creates a pending AI conversation before the MQTT command is published. */
    public static Conversation requestForScenario(
        UUID seniorId,
        UUID scenarioId,
        String startCommandId,
        OffsetDateTime requestedAt
    ) {
        Conversation conversation = new Conversation(
            seniorId,
            requireNonNull(scenarioId, "scenarioId"),
            requestedAt
        );

        conversation.startCommandId = requireText(
            startCommandId,
            "startCommandId",
            64
        );

        return conversation;
    }

    /** Marks the AI acknowledgement; returns false for a duplicate acknowledgement. */
    public boolean markAiStarted(OffsetDateTime occurredAt) {
        requireNonNull(occurredAt, "occurredAt");

        if (status != ConversationStatus.OPEN) {
            return false;
        }

        if (aiStartedAt != null) {
            return false;
        }

        this.aiStartedAt = occurredAt;
        return true;
    }

    /** Marks the conversation ended with a terminal status (COMPLETED/FAILED/CANCELLED). */
    public void end(ConversationStatus terminalStatus) {
        if (terminalStatus == null || terminalStatus == ConversationStatus.OPEN) {
            throw new IllegalArgumentException(
                "terminalStatus must be a terminal status"
            );
        }

        ConversationOutcome outcome = switch (terminalStatus) {
            case COMPLETED -> ConversationOutcome.COMPLETED;
            case FAILED -> ConversationOutcome.FAILED;
            case CANCELLED -> ConversationOutcome.CANCELLED;
            case OPEN -> throw new IllegalArgumentException(
                "terminalStatus must be terminal"
            );
        };

        end(
            outcome,
            outcome == ConversationOutcome.FAILED
                ? "UNSPECIFIED_FAILURE"
                : null,
            OffsetDateTime.now()
        );
    }

    /** Applies the exact AI/backend outcome; returns false when already terminal. */
    public boolean end(
        ConversationOutcome outcome,
        String reasonCode,
        OffsetDateTime occurredAt
    ) {
        requireNonNull(outcome, "outcome");
        requireNonNull(occurredAt, "occurredAt");

        String normalizedReason = normalizeReason(reasonCode);

        if (
            outcome == ConversationOutcome.FAILED
                && normalizedReason == null
        ) {
            throw new IllegalArgumentException(
                "reasonCode is required for FAILED conversation"
            );
        }

        if (status != ConversationStatus.OPEN) {
            return false;
        }

        this.status = switch (outcome) {
            case COMPLETED, NO_RESPONSE -> ConversationStatus.COMPLETED;
            case CANCELLED -> ConversationStatus.CANCELLED;
            case FAILED -> ConversationStatus.FAILED;
        };

        this.endOutcome = outcome;
        this.reasonCode = normalizedReason;
        this.endedAt = occurredAt;

        return true;
    }

    public void scheduleRawExpiry(OffsetDateTime expiresAt) {
        this.rawMessagesExpiresAt = expiresAt;
    }

    public boolean isOpen() {
        return status == ConversationStatus.OPEN;
    }

    public boolean hasAiStarted() {
        return aiStartedAt != null;
    }

    /** 이 대화를 봉인한다. 되돌릴 수 없다. */
    public void markSealed() {
        this.sealed = true;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(
                field + " must not be null"
            );
        }

        return value;
    }

    private static String requireText(
        String value,
        String field,
        int maxLength
    ) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                field + " must not be blank"
            );
        }

        if (value.length() > maxLength) {
            throw new IllegalArgumentException(
                field + " must not exceed " + maxLength + " characters"
            );
        }

        return value;
    }

    private static String normalizeReason(String value) {
        if (value == null) {
            return null;
        }

        String normalized = value.trim();

        if (normalized.isEmpty()) {
            return null;
        }

        if (normalized.length() > 100) {
            throw new IllegalArgumentException(
                "reasonCode must not exceed 100 characters"
            );
        }

        return normalized;
    }
}
