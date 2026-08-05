package com.ssafy.bomi.guardian.dto;

import com.ssafy.bomi.scenario.application.WalkRequestResult;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.WalkAction;
import java.util.UUID;

public record GuardianWalkResponse(
    String requestId,
    WalkAction action,
    boolean accepted,
    UUID scenarioId,
    ScenarioStatus status,
    String reasonCode,
    boolean duplicate
) {
    public static GuardianWalkResponse from(WalkRequestResult result) {
        return new GuardianWalkResponse(
            result.requestId(), result.action(), result.accepted(), result.scenarioId(),
            result.status(), result.reasonCode(), result.duplicate());
    }
}
