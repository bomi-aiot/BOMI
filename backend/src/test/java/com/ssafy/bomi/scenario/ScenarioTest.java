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

    private Scenario newWakeWordCall() {
        return Scenario.create(
            UUID.randomUUID(), UUID.randomUUID(), ScenarioType.WAKE_WORD_CALL, "evt-wake-01");
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
    void allowsReturnWhenAiFailsBeforeConversationStarted() {
        Scenario scenario = newHomecoming();
        scenario.beginMovingToEntrance();
        scenario.checkInteraction();

        scenario.decideReturn();
        scenario.returnToDefault();

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
    }

    @Test
    void rejectsTransitionFromTerminalState() {
        Scenario scenario = newHomecoming();
        scenario.cancel();
        assertThat(scenario.isTerminated()).isTrue();
        assertThatThrownBy(scenario::beginMovingToEntrance)
            .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void wakeWordCallNavigatesDirectlyToCompletedWithoutConversationStates() {
        Scenario scenario = newWakeWordCall();
        scenario.recordTriggerContext(java.util.Map.of(
            "keyword", "보미야",
            "occurredAt", "2026-08-05T10:00:00+09:00"));
        scenario.beginNavigation();
        scenario.expectNavigationResult("cmd-wake-01", "LIVING_ROOM");

        scenario.complete("ARRIVED", null);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getCompletionResultCode()).isEqualTo("ARRIVED");
        assertThat(scenario.getCompletionReasonCode()).isNull();
        assertThat(scenario.getActiveNavigationCommandId()).isNull();
        assertThat(scenario.getTriggerContext()).containsEntry("keyword", "보미야");
    }

    @Test
    void wakeWordCallCannotEnterTheConversationFlow() {
        Scenario scenario = newWakeWordCall();

        assertThatThrownBy(scenario::beginMovingToEntrance)
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(scenario::beginConversation)
            .isInstanceOf(IllegalStateException.class);
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RECEIVED);
    }

    @Test
    void conversationScenarioCannotEnterWakeWordNavigationState() {
        assertThatThrownBy(newHomecoming()::beginNavigation)
            .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void wakeWordFailurePreservesStructuredResultAndReason() {
        Scenario scenario = newWakeWordCall();
        scenario.beginNavigation();
        scenario.expectNavigationResult("cmd-wake-02", "LIVING_ROOM");

        scenario.fail("NOT_ARRIVED", "PATH_BLOCKED");

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FAILED);
        assertThat(scenario.getCompletionResultCode()).isEqualTo("NOT_ARRIVED");
        assertThat(scenario.getCompletionReasonCode()).isEqualTo("PATH_BLOCKED");
    }
}
