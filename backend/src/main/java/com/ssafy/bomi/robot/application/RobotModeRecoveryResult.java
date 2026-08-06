package com.ssafy.bomi.robot.application;

import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryDisposition;
import java.time.OffsetDateTime;
import java.util.UUID;

/** Structured outcome of one operator recovery attempt. */
public record RobotModeRecoveryResult(
    RobotModeRecoveryDisposition disposition,
    UUID robotId,
    String robotDeviceId,
    RobotMode previousMode,
    RobotMode currentMode,
    UUID auditId,
    OffsetDateTime recoveredAt,
    String message
) {
    public boolean accepted() {
        return disposition.accepted();
    }
}
