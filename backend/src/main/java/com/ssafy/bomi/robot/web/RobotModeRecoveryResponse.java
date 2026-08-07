package com.ssafy.bomi.robot.web;

import com.ssafy.bomi.robot.application.RobotModeRecoveryResult;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryDisposition;
import java.time.OffsetDateTime;
import java.util.UUID;

/** Operator-facing recovery result. The only supported target mode is {@code IDLE}. */
public record RobotModeRecoveryResponse(
    RobotModeRecoveryDisposition disposition,
    UUID robotId,
    String robotDeviceId,
    RobotMode previousMode,
    RobotMode currentMode,
    UUID auditId,
    OffsetDateTime recoveredAt,
    String message
) {
    public static RobotModeRecoveryResponse from(RobotModeRecoveryResult result) {
        return new RobotModeRecoveryResponse(
            result.disposition(),
            result.robotId(),
            result.robotDeviceId(),
            result.previousMode(),
            result.currentMode(),
            result.auditId(),
            result.recoveredAt(),
            result.message());
    }
}
