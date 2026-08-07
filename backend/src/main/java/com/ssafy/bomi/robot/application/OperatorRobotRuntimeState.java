package com.ssafy.bomi.robot.application;

import com.ssafy.bomi.robot.domain.OccupancyStatus;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

/** Read-only runtime snapshot for the authenticated operator console. */
public record OperatorRobotRuntimeState(
    UUID robotId,
    String robotDeviceId,
    boolean active,
    UUID seniorId,
    RobotMode currentMode,
    OccupancyStatus occupancyStatus,
    OffsetDateTime occupancyObservedAt,
    OffsetDateTime doorNodeHeartbeatAt,
    List<ActiveScenario> activeScenarios,
    OffsetDateTime observedAt
) {
    public record ActiveScenario(
        UUID scenarioId,
        ScenarioType scenarioType,
        ScenarioStatus status,
        String navigationTarget,
        String navigationCommandId,
        OffsetDateTime updatedAt
    ) {
    }
}
