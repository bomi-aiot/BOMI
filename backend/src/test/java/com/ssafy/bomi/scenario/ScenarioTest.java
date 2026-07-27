package com.ssafy.bomi.scenario;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/**
 * Pure-domain unit tests for the {@link Scenario} state machine (no persistence).
 */
class ScenarioTest {

    private Scenario newHomecoming() {
        return Scenario.create(UUID.randomUUID(), UUID.randomUUID(), ScenarioType.HOMECOMING);
    }

    @Test
    void startsAtReceived() {
        Scenario scenario = newHomecoming();
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RECEIVED);
        assertThat(scenario.isTerminated()).isFalse();
    }

    @Test
    void walksHomecomingHappyPathToCompleted() {
        Scenario scenario = newHomecoming();
        scenario.beginMovingToEntrance();
        scenario.checkInteraction();
        scenario.beginConversation();
        scenario.decideReturn();
        scenario.returnToDefault();
        scenario.complete();

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.isTerminated()).isTrue();
    }

    @Test
    void rejectsSkippingSteps() {
        Scenario scenario = newHomecoming();
        // RECEIVED -> CONVERSING is not allowed (must go through the linear path).
        assertThatThrownBy(scenario::beginConversation)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("Illegal scenario transition");
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RECEIVED);
    }

    @Test
    void allowsTerminalExitFromActiveState() {
        Scenario scenario = newHomecoming();
        scenario.beginMovingToEntrance();
        scenario.fail();
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FAILED);
    }

    @Test
    void rejectsTransitionFromTerminalState() {
        Scenario scenario = newHomecoming();
        scenario.cancel();
        assertThat(scenario.isTerminated()).isTrue();
        assertThatThrownBy(scenario::beginMovingToEntrance)
            .isInstanceOf(IllegalStateException.class);
    }
}
