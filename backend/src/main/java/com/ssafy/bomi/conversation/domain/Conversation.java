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

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
