package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import org.junit.jupiter.api.Test;

class RobotModePolicyTest {

    @Test
    void activeStatusesMapToScenarioActive() {
        assertThat(RobotModePolicy.forScenario(ScenarioStatus.RECEIVED)).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(RobotModePolicy.forScenario(ScenarioStatus.MOVING_TO_ENTRANCE))
            .isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(RobotModePolicy.forScenario(ScenarioStatus.CONVERSING)).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(RobotModePolicy.forScenario(ScenarioStatus.RETURNING_TO_DEFAULT))
            .isEqualTo(RobotMode.SCENARIO_ACTIVE);
    }

    @Test
    void completedMapsToIdle() {
        assertThat(RobotModePolicy.forScenario(ScenarioStatus.COMPLETED)).isEqualTo(RobotMode.IDLE);
    }

    @Test
    void terminalFailuresMapToSafeStop() {
        assertThat(RobotModePolicy.forScenario(ScenarioStatus.FAILED)).isEqualTo(RobotMode.SAFE_STOP);
        assertThat(RobotModePolicy.forScenario(ScenarioStatus.CANCELLED)).isEqualTo(RobotMode.SAFE_STOP);
        assertThat(RobotModePolicy.forScenario(ScenarioStatus.TIMED_OUT)).isEqualTo(RobotMode.SAFE_STOP);
    }
}
