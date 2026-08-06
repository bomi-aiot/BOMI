package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.WalkAction;
import com.ssafy.bomi.scenario.domain.WalkRequestDisposition;
import java.util.UUID;

/** Deterministic application result used by both MQTT and Guardian REST adapters. */
public record WalkRequestResult(
    String requestId,
    WalkAction action,
    boolean accepted,
    UUID scenarioId,
    ScenarioStatus status,
    String reasonCode,
    boolean duplicate,
    WalkRequestDisposition disposition
) {
}
