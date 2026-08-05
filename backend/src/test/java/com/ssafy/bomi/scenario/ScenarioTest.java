package com.ssafy.bomi.scenario;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import java.time.OffsetDateTime;
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

    private Scenario newWalk() {
        return Scenario.create(
            UUID.randomUUID(), UUID.randomUUID(), ScenarioType.WALK, "walk-request-01");
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

    @Test
    void walkFollowsItsOwnHappyPathAndPreservesBothCommandCorrelations() {
        Scenario scenario = newWalk();
        OffsetDateTime startAt = OffsetDateTime.parse("2026-08-05T16:00:00+09:00");
        OffsetDateTime startedAt = startAt.plusSeconds(2);
        OffsetDateTime stopAt = startAt.plusMinutes(30);

        scenario.beginFollowStart("cmd-follow-start-01", startAt);
        scenario.confirmFollowing(
            "evt-follow-started-01",
            "cmd-follow-start-01",
            "STARTED",
            null,
            startedAt,
            startedAt);
        scenario.beginFollowStop("cmd-follow-stop-01", stopAt);
        scenario.recordFollowResult(
            "evt-follow-stopped-01",
            "cmd-follow-stop-01",
            "STOPPED",
            null,
            stopAt.plusSeconds(1));
        scenario.complete("STOPPED", null);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getFollowStartCommandId()).isEqualTo("cmd-follow-start-01");
        assertThat(scenario.getFollowStopCommandId()).isEqualTo("cmd-follow-stop-01");
        assertThat(scenario.getFollowingStartedAt()).isEqualTo(startedAt);
        assertThat(scenario.getCompletionResultCode()).isEqualTo("STOPPED");
        assertThat(scenario.getLastFollowResultEventId())
            .isEqualTo("evt-follow-stopped-01");
    }

    @Test
    void walkCanRecordStartedWhileStoppingWithoutReturningToFollowing() {
        Scenario scenario = newWalk();
        OffsetDateTime now = OffsetDateTime.parse("2026-08-05T16:00:00+09:00");
        scenario.beginFollowStart("cmd-follow-start-02", now);
        scenario.beginFollowStop("cmd-follow-stop-02", now.plusSeconds(1));

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThatThrownBy(() -> scenario.confirmFollowing(
            "evt-late-started",
            "cmd-follow-start-02",
            "STARTED",
            null,
            now.plusSeconds(2),
            now.plusSeconds(2)))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("Illegal scenario transition");

        scenario.confirmFollowStartWhileStopping(
            "evt-late-started",
            "cmd-follow-start-02",
            "STARTED",
            null,
            now.plusSeconds(2),
            now.plusSeconds(2));
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThat(scenario.getFollowingStartedAt()).isEqualTo(now.plusSeconds(2));
        assertThat(scenario.getLastFollowResultEventId()).isEqualTo("evt-late-started");
    }

    @Test
    void walkSelfStoppedFromFollowingCanCompleteWithoutFollowStopCommand() {
        Scenario scenario = newWalk();
        OffsetDateTime now = OffsetDateTime.parse("2026-08-05T16:00:00+09:00");
        scenario.beginFollowStart("cmd-follow-start-self", now);
        scenario.confirmFollowing(
            "evt-started-self", "cmd-follow-start-self", "STARTED", null,
            now.plusSeconds(1), now.plusSeconds(1));
        scenario.recordFollowResult(
            "evt-self-stopped", "cmd-follow-start-self", "STOPPED", null,
            now.plusMinutes(10));

        scenario.complete("STOPPED", null);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getFollowStopCommandId()).isNull();
        assertThat(scenario.getLastFollowCommandId()).isEqualTo("cmd-follow-start-self");
    }

    @Test
    void walkAllowsExceptionalTerminalExitFromEveryActiveState() {
        OffsetDateTime now = OffsetDateTime.parse("2026-08-05T16:00:00+09:00");

        Scenario received = newWalk();
        received.fail("UNCHANGED", "INTERNAL_ERROR");

        Scenario starting = newWalk();
        starting.beginFollowStart("cmd-starting", now);
        starting.cancel("UNCHANGED", "SAFETY_STOP");

        Scenario following = newWalk();
        following.beginFollowStart("cmd-following", now);
        following.confirmFollowing(
            "evt-following", "cmd-following", "STARTED", null, now, now);
        following.timeOut("STOPPED", "EXECUTION_TIMEOUT");

        Scenario stopping = newWalk();
        stopping.beginFollowStart("cmd-start-stop", now);
        stopping.beginFollowStop("cmd-stop-timeout", now.plusSeconds(1));
        stopping.timeOut("UNCHANGED", "EXECUTION_TIMEOUT");

        assertThat(received.getFinalStatus()).isEqualTo(ScenarioStatus.FAILED);
        assertThat(starting.getFinalStatus()).isEqualTo(ScenarioStatus.CANCELLED);
        assertThat(following.getFinalStatus()).isEqualTo(ScenarioStatus.TIMED_OUT);
        assertThat(stopping.getFinalStatus()).isEqualTo(ScenarioStatus.TIMED_OUT);
    }

    @Test
    void walkRequiresDistinctStartAndStopCommandIds() {
        Scenario scenario = newWalk();
        OffsetDateTime now = OffsetDateTime.parse("2026-08-05T16:00:00+09:00");
        scenario.beginFollowStart("cmd-same", now);

        assertThatThrownBy(() -> scenario.beginFollowStop("cmd-same", now.plusSeconds(1)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("must differ");
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STARTING_FOLLOW);
        assertThat(scenario.getFollowStopCommandId()).isNull();
    }

    @Test
    void walkStatesAreIsolatedFromConversationAndWakeWordTypes() {
        OffsetDateTime now = OffsetDateTime.parse("2026-08-05T16:00:00+09:00");
        Scenario walk = newWalk();

        assertThatThrownBy(walk::beginMovingToEntrance)
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(walk::beginNavigation)
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> newHomecoming().beginFollowStart("cmd-home", now))
            .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> newWakeWordCall().beginFollowStart("cmd-wake", now))
            .isInstanceOf(IllegalStateException.class);
    }
}
