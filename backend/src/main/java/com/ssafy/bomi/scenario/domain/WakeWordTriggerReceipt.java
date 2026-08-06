package com.ssafy.bomi.scenario.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;

/** Durable idempotency receipt for one wake-word trigger, including rejections. */
@Entity
@Table(name = "wake_word_trigger_receipt")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class WakeWordTriggerReceipt {

    @Id
    @Column(name = "event_id", nullable = false, updatable = false, length = 64)
    private String eventId;

    @Column(name = "robot_device_id", nullable = false, updatable = false, length = 64)
    private String robotDeviceId;

    @Column(name = "occurred_at", nullable = false, updatable = false)
    private OffsetDateTime occurredAt;

    @Column(name = "keyword", nullable = false, updatable = false, length = 20)
    private String keyword;

    @Column(name = "confidence", updatable = false)
    private Double confidence;

    @Enumerated(EnumType.STRING)
    @Column(name = "disposition", nullable = false, length = 40)
    private WakeWordTriggerDisposition disposition;

    @Column(name = "scenario_id")
    private UUID scenarioId;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    private WakeWordTriggerReceipt(
        String eventId,
        String robotDeviceId,
        OffsetDateTime occurredAt,
        String keyword,
        Double confidence
    ) {
        this.eventId = requireText(eventId, "eventId", 64);
        this.robotDeviceId = requireText(robotDeviceId, "robotDeviceId", 64);
        this.occurredAt = Objects.requireNonNull(occurredAt, "occurredAt");
        this.keyword = requireText(keyword, "keyword", 20);
        if (confidence != null && (!Double.isFinite(confidence)
            || confidence < 0 || confidence > 1)) {
            throw new IllegalArgumentException("confidence must be between 0 and 1");
        }
        this.confidence = confidence;
        this.disposition = WakeWordTriggerDisposition.RECEIVED;
    }

    public static WakeWordTriggerReceipt receive(
        String eventId,
        String robotDeviceId,
        OffsetDateTime occurredAt,
        String keyword,
        Double confidence
    ) {
        return new WakeWordTriggerReceipt(
            eventId, robotDeviceId, occurredAt, keyword, confidence);
    }

    public void accept(UUID scenarioId) {
        resolve(WakeWordTriggerDisposition.ACCEPTED,
            Objects.requireNonNull(scenarioId, "scenarioId"));
    }

    public void reject(WakeWordTriggerDisposition rejection) {
        if (rejection == null
            || rejection == WakeWordTriggerDisposition.RECEIVED
            || rejection == WakeWordTriggerDisposition.ACCEPTED) {
            throw new IllegalArgumentException("A rejected disposition is required");
        }
        resolve(rejection, null);
    }

    public boolean describes(
        String robotDeviceId,
        OffsetDateTime occurredAt,
        String keyword,
        Double confidence
    ) {
        return this.robotDeviceId.equals(robotDeviceId)
            && this.occurredAt.toInstant().equals(occurredAt.toInstant())
            && this.keyword.equals(keyword)
            && Objects.equals(this.confidence, confidence);
    }

    private void resolve(WakeWordTriggerDisposition next, UUID scenarioId) {
        if (disposition != WakeWordTriggerDisposition.RECEIVED) {
            throw new IllegalStateException("Wake-word trigger receipt is already resolved");
        }
        this.disposition = next;
        this.scenarioId = scenarioId;
    }

    private static String requireText(String value, String field, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(
                field + " must not exceed " + maxLength + " characters");
        }
        return value;
    }
}
