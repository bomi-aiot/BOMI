package com.ssafy.bomi.scenario.domain;

import com.ssafy.bomi.robot.domain.RobotMode;
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

/** Immutable audit of an authenticated operator cancellation. */
@Entity
@Table(name = "operator_scenario_cancellation_audit")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class OperatorScenarioCancellationAudit {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "robot_id", nullable = false, updatable = false)
    private UUID robotId;

    @Column(name = "robot_device_id", nullable = false, updatable = false, length = 64)
    private String robotDeviceId;

    @Column(name = "scenario_id", nullable = false, updatable = false)
    private UUID scenarioId;

    @Column(name = "operator_id", nullable = false, updatable = false, length = 100)
    private String operatorId;

    @Enumerated(EnumType.STRING)
    @Column(name = "previous_scenario_status", nullable = false, updatable = false, length = 50)
    private ScenarioStatus previousScenarioStatus;

    @Enumerated(EnumType.STRING)
    @Column(name = "previous_robot_mode", nullable = false, updatable = false, length = 30)
    private RobotMode previousRobotMode;

    @Column(name = "target_navigation_command_id", updatable = false, length = 64)
    private String targetNavigationCommandId;

    @Column(name = "cancel_command_id", updatable = false, length = 64)
    private String cancelCommandId;

    @Column(name = "physical_safety_confirmed", nullable = false, updatable = false)
    private boolean physicalSafetyConfirmed;

    @Column(name = "reason", nullable = false, updatable = false, length = 500)
    private String reason;

    @Column(name = "cancelled_at", nullable = false, updatable = false)
    private OffsetDateTime cancelledAt;

    public static OperatorScenarioCancellationAudit record(
        UUID robotId, String robotDeviceId, UUID scenarioId, String operatorId,
        ScenarioStatus previousScenarioStatus, RobotMode previousRobotMode,
        String targetNavigationCommandId, String cancelCommandId, String reason,
        OffsetDateTime cancelledAt
    ) {
        OperatorScenarioCancellationAudit audit = new OperatorScenarioCancellationAudit();
        audit.robotId = require(robotId, "robotId");
        audit.robotDeviceId = text(robotDeviceId, "robotDeviceId", 64);
        audit.scenarioId = require(scenarioId, "scenarioId");
        audit.operatorId = text(operatorId, "operatorId", 100);
        audit.previousScenarioStatus = require(previousScenarioStatus, "previousScenarioStatus");
        audit.previousRobotMode = require(previousRobotMode, "previousRobotMode");
        audit.targetNavigationCommandId = optionalText(targetNavigationCommandId,
            "targetNavigationCommandId", 64);
        audit.cancelCommandId = optionalText(cancelCommandId, "cancelCommandId", 64);
        audit.physicalSafetyConfirmed = true;
        audit.reason = text(reason, "reason", 500);
        audit.cancelledAt = require(cancelledAt, "cancelledAt");
        return audit;
    }

    private static <T> T require(T value, String field) {
        if (value == null) throw new IllegalArgumentException(field + " must not be null");
        return value;
    }

    private static String text(String value, String field, int max) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        String normalized = value.trim();
        if (normalized.length() > max) {
            throw new IllegalArgumentException(field + " must not exceed " + max + " characters");
        }
        return normalized;
    }

    private static String optionalText(String value, String field, int max) {
        return value == null ? null : text(value, field, max);
    }
}
