package com.ssafy.bomi.scenario.web;

import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.scenario.application.OperatorScenarioCancellationResult;
import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationDisposition;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import java.time.OffsetDateTime;
import java.util.UUID;

public record OperatorScenarioCancellationResponse(
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
    static OperatorScenarioCancellationResponse from(OperatorScenarioCancellationResult result) {
        return new OperatorScenarioCancellationResponse(
            result.disposition(), result.robotId(), result.robotDeviceId(), result.scenarioId(),
            result.previousScenarioStatus(), result.currentScenarioStatus(), result.previousMode(),
            result.currentMode(), result.cancelCommandId(), result.auditId(), result.cancelledAt(),
            result.message());
    }
}
