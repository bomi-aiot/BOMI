package com.ssafy.bomi.robot.domain;

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

/** Immutable audit record for an authenticated operator mode recovery. */
@Entity
@Table(name = "robot_mode_recovery_audit")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class RobotModeRecoveryAudit {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "robot_id", nullable = false, updatable = false)
    private UUID robotId;

    @Column(name = "robot_device_id", nullable = false, updatable = false, length = 64)
    private String robotDeviceId;

    @Column(name = "operator_id", nullable = false, updatable = false, length = 100)
    private String operatorId;

    @Enumerated(EnumType.STRING)
    @Column(name = "previous_mode", nullable = false, updatable = false, length = 30)
    private RobotMode previousMode;

    @Enumerated(EnumType.STRING)
    @Column(name = "target_mode", nullable = false, updatable = false, length = 30)
    private RobotMode targetMode;

    @Enumerated(EnumType.STRING)
    @Column(name = "disposition", nullable = false, updatable = false, length = 30)
    private RobotModeRecoveryDisposition disposition;

    @Column(name = "physical_safety_confirmed", nullable = false, updatable = false)
    private boolean physicalSafetyConfirmed;

    @Column(name = "reason", nullable = false, updatable = false, length = 500)
    private String reason;

    @Column(name = "recovered_at", nullable = false, updatable = false)
    private OffsetDateTime recoveredAt;

    private RobotModeRecoveryAudit(
        UUID robotId,
        String robotDeviceId,
        String operatorId,
        RobotMode previousMode,
        RobotModeRecoveryDisposition disposition,
        String reason,
        OffsetDateTime recoveredAt
    ) {
        this.robotId = requireNonNull(robotId, "robotId");
        this.robotDeviceId = requireText(robotDeviceId, "robotDeviceId", 64);
        this.operatorId = requireText(operatorId, "operatorId", 100);
        this.previousMode = requireNonNull(previousMode, "previousMode");
        this.targetMode = RobotMode.IDLE;
        this.disposition = requireNonNull(disposition, "disposition");
        if (!disposition.accepted()) {
            throw new IllegalArgumentException("only accepted recoveries may be audited");
        }
        this.physicalSafetyConfirmed = true;
        this.reason = requireText(reason, "reason", 500);
        this.recoveredAt = requireNonNull(recoveredAt, "recoveredAt");
    }

    public static RobotModeRecoveryAudit record(
        Robot robot,
        String operatorId,
        RobotMode previousMode,
        RobotModeRecoveryDisposition disposition,
        String reason,
        OffsetDateTime recoveredAt
    ) {
        if (robot == null) {
            throw new IllegalArgumentException("robot must not be null");
        }
        return new RobotModeRecoveryAudit(
            robot.getId(),
            robot.getDeviceId(),
            operatorId,
            previousMode,
            disposition,
            reason,
            recoveredAt);
    }

    public UUID getId() {
        return id;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }

    private static String requireText(String value, String field, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        String normalized = value.trim();
        if (normalized.length() > maxLength) {
            throw new IllegalArgumentException(
                field + " must not exceed " + maxLength + " characters");
        }
        return normalized;
    }
}
