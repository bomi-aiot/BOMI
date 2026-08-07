package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;

/**
 * Maps a scenario's current status to the robot mode it implies.
 *
 * <p>Scenario-driven modes only: any active status means the robot is busy with
 * a scenario ({@code SCENARIO_ACTIVE}); a normal completion returns it to
 * {@code IDLE}; a failed/cancelled/timed-out scenario forces {@code SAFE_STOP}.
 * The rest-monitoring mode ({@code REST_GUARD}) is orthogonal and driven by rest
 * observations, not by scenario status.</p>
 */
public final class RobotModePolicy {

    private RobotModePolicy() {
    }

    public static RobotMode forScenario(ScenarioStatus status) {
        return switch (status) {
            case COMPLETED -> RobotMode.IDLE;
            case FAILED, CANCELLED, TIMED_OUT -> RobotMode.SAFE_STOP;
            default -> RobotMode.SCENARIO_ACTIVE; // RECEIVED..RETURNING_TO_DEFAULT
        };
    }
}
