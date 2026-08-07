package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationDisposition;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import java.time.OffsetDateTime;
import java.util.UUID;

public record OperatorScenarioCancellationResult(
    OperatorScenarioCancellationDisposition disposition,
    UUID robotId,
    String robotDeviceId,
    UUID scenarioId,
    ScenarioStatus previousScenarioStatus,
    ScenarioStatus currentScenarioStatus,
    RobotMode previousMode,
    RobotMode currentMode,
    String cancelCommandId,
    UUID auditId,
    OffsetDateTime cancelledAt,
    String message
) {
    public boolean accepted() {
        return disposition.accepted();
    }
}
