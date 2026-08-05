package com.ssafy.bomi.scenario.domain;

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
import java.util.Objects;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;

/** Durable decision and deterministic response for one Voice/Guardian walk request. */
@Entity
@Table(
    name = "walk_request_receipt",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_walk_request_ingress_request",
        columnNames = {"ingress", "request_id"}))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class WalkRequestReceipt {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Enumerated(EnumType.STRING)
    @Column(name = "ingress", nullable = false, updatable = false, length = 30)
    private WalkRequestIngress ingress;

    @Column(name = "request_id", nullable = false, updatable = false, length = 64)
    private String requestId;

    @Column(name = "robot_device_id", nullable = false, updatable = false, length = 64)
    private String robotDeviceId;

    @Enumerated(EnumType.STRING)
    @Column(name = "action", nullable = false, updatable = false, length = 10)
    private WalkAction action;

    @Enumerated(EnumType.STRING)
    @Column(name = "source", nullable = false, updatable = false, length = 10)
    private WalkRequestSource source;

    @Column(name = "conversation_id", updatable = false)
    private UUID conversationId;

    @Column(name = "occurred_at", nullable = false, updatable = false)
    private OffsetDateTime occurredAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "disposition", nullable = false, length = 50)
    private WalkRequestDisposition disposition;

    @Column(name = "scenario_id")
    private UUID scenarioId;

    @Enumerated(EnumType.STRING)
    @Column(name = "scenario_status", length = 50)
    private ScenarioStatus scenarioStatus;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    private WalkRequestReceipt(
        WalkRequestIngress ingress,
        String requestId,
        String robotDeviceId,
        WalkAction action,
        WalkRequestSource source,
        UUID conversationId,
        OffsetDateTime occurredAt
    ) {
        this.ingress = Objects.requireNonNull(ingress, "ingress");
        this.requestId = requireText(requestId, "requestId", 64);
        this.robotDeviceId = requireText(robotDeviceId, "robotDeviceId", 64);
        this.action = Objects.requireNonNull(action, "action");
        this.source = Objects.requireNonNull(source, "source");
        this.conversationId = conversationId;
        this.occurredAt = Objects.requireNonNull(occurredAt, "occurredAt");
        this.disposition = WalkRequestDisposition.RECEIVED;
    }

    public static WalkRequestReceipt receive(
        WalkRequestIngress ingress,
        String requestId,
        String robotDeviceId,
        WalkAction action,
        WalkRequestSource source,
        UUID conversationId,
        OffsetDateTime occurredAt
    ) {
        return new WalkRequestReceipt(
            ingress, requestId, robotDeviceId, action, source, conversationId, occurredAt);
    }

    public void resolve(
        WalkRequestDisposition disposition,
        UUID scenarioId,
        ScenarioStatus scenarioStatus
    ) {
        if (this.disposition != WalkRequestDisposition.RECEIVED) {
            throw new IllegalStateException("Walk request receipt is already resolved");
        }
        if (disposition == null || disposition == WalkRequestDisposition.RECEIVED) {
            throw new IllegalArgumentException("A final walk request disposition is required");
        }
        if (disposition.isAccepted() && (scenarioId == null || scenarioStatus == null)) {
            throw new IllegalArgumentException("Accepted walk request requires scenario response");
        }
        if (!disposition.isAccepted() && (scenarioId != null || scenarioStatus != null)) {
            throw new IllegalArgumentException("Rejected walk request must not expose a scenario");
        }
        this.disposition = disposition;
        this.scenarioId = scenarioId;
        this.scenarioStatus = scenarioStatus;
    }

    public boolean describes(
        String robotDeviceId,
        WalkAction action,
        WalkRequestSource source,
        UUID conversationId,
        OffsetDateTime occurredAt
    ) {
        boolean sameCore = this.robotDeviceId.equals(robotDeviceId)
            && this.action == action
            && this.source == source
            && Objects.equals(this.conversationId, conversationId);
        if (!sameCore) {
            return false;
        }
        // Guardian REST retries do not carry occurredAt; Backend creates a new now on every HTTP
        // attempt. MQTT retries must preserve the producer timestamp and are checked strictly.
        return ingress == WalkRequestIngress.GUARDIAN_REST
            || this.occurredAt.toInstant().equals(occurredAt.toInstant());
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
