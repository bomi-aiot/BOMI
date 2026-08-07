package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.WalkTimeoutProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class WalkTimeoutWatchdogTest {

    private static final OffsetDateTime NOW =
        OffsetDateTime.parse("2026-08-05T16:00:00+09:00");

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final WalkTimeoutProperties properties = new WalkTimeoutProperties();
    private final RecordingPublisher publisher = new RecordingPublisher();
    private final Clock clock = Clock.fixed(
        Instant.parse("2026-08-05T07:00:00Z"), ZoneOffset.UTC);

    private WalkTimeoutWatchdog watchdog() {
        return new WalkTimeoutWatchdog(
            scenarioRepository, robotRepository, publisher, properties, clock);
    }

    @Test
    void startAckTimeoutSendsOneBestEffortStopAndEndsTimedOutSafeStop() {
        Scenario scenario = startingWalk(NOW.minusSeconds(11));
        Robot robot = robotFor(scenario);
        when(scenarioRepository.findActiveWalksForUpdate(anyCollection()))
            .thenReturn(List.of(scenario));
        when(robotRepository.findByIdForUpdate(scenario.getRobotId()))
            .thenReturn(Optional.of(robot));

        watchdog().tick();

        assertTimedOut(scenario, robot);
        assertThat(scenario.getFollowStopCommandId()).isNotBlank()
            .isNotEqualTo(scenario.getFollowStartCommandId());
        assertThat(publisher.commands).singleElement().satisfies(command -> {
            assertThat(command.type()).isEqualTo(RobotCommandType.FOLLOW_STOP);
            assertThat(command.commandId()).isEqualTo(scenario.getFollowStopCommandId());
            assertThat(command.payload()).isEmpty();
        });
    }

    @Test
    void stopAckTimeoutRetriesThePersistedStopCommandIdAndEndsTimedOut() {
        Scenario scenario = followingWalk(NOW.minusMinutes(5), NOW.minusMinutes(4));
        scenario.beginFollowStop("cmd-follow-stop-timeout", NOW.minusSeconds(11));
        Robot robot = robotFor(scenario);
        when(scenarioRepository.findActiveWalksForUpdate(anyCollection()))
            .thenReturn(List.of(scenario));
        when(robotRepository.findByIdForUpdate(scenario.getRobotId()))
            .thenReturn(Optional.of(robot));

        watchdog().tick();

        assertTimedOut(scenario, robot);
        assertThat(scenario.getFollowStopCommandId()).isEqualTo("cmd-follow-stop-timeout");
        assertThat(publisher.commands).singleElement()
            .extracting(RobotCommand::commandId)
            .isEqualTo("cmd-follow-stop-timeout");
    }

    @Test
    void stopRequestedBeforeStartedUsesStartAckDeadlineThenSendsPersistedStop() {
        Scenario scenario = startingWalk(NOW.minusSeconds(11));
        scenario.beginFollowStop("cmd-deferred-stop-timeout", NOW.minusSeconds(1));
        Robot robot = robotFor(scenario);
        when(scenarioRepository.findActiveWalksForUpdate(anyCollection()))
            .thenReturn(List.of(scenario));
        when(robotRepository.findByIdForUpdate(scenario.getRobotId()))
            .thenReturn(Optional.of(robot));

        watchdog().tick();

        assertTimedOut(scenario, robot);
        assertThat(publisher.commands).singleElement()
            .extracting(RobotCommand::commandId)
            .isEqualTo("cmd-deferred-stop-timeout");
    }

    @Test
    void deferredStopAckTimeoutStartsWhenStartAckAllowsStopPublication() {
        Scenario scenario = startingWalk(NOW.minusSeconds(9));
        scenario.beginFollowStop("cmd-deferred-stop-fresh", NOW.minusSeconds(8));
        scenario.confirmFollowStartWhileStopping(
            "evt-deferred-started",
            scenario.getFollowStartCommandId(),
            "STARTED",
            null,
            NOW.minusSeconds(1),
            NOW.minusSeconds(1));
        when(scenarioRepository.findActiveWalksForUpdate(anyCollection()))
            .thenReturn(List.of(scenario));

        watchdog().tick();

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.STOPPING_FOLLOW);
        assertThat(publisher.commands).isEmpty();
        verify(scenarioRepository, never()).save(scenario);
    }

    @Test
    void wholeWalkMaxDurationCountsFromStartRequestNotFromStartedAck() {
        properties.setMaxDuration(Duration.ofMinutes(30));
        Scenario scenario = followingWalk(NOW.minusMinutes(31), NOW.minusMinutes(1));
        Robot robot = robotFor(scenario);
        when(scenarioRepository.findActiveWalksForUpdate(anyCollection()))
            .thenReturn(List.of(scenario));
        when(robotRepository.findByIdForUpdate(scenario.getRobotId()))
            .thenReturn(Optional.of(robot));

        watchdog().tick();

        assertTimedOut(scenario, robot);
        assertThat(publisher.commands).singleElement()
            .extracting(RobotCommand::type)
            .isEqualTo(RobotCommandType.FOLLOW_STOP);
    }

    @Test
    void wholeWalkHardDeadlineStillAppliesWhileFreshStopAckIsPending() {
        properties.setMaxDuration(Duration.ofMinutes(30));
        Scenario scenario = followingWalk(NOW.minusMinutes(31), NOW.minusMinutes(1));
        scenario.beginFollowStop("cmd-stop-fresh", NOW.minusSeconds(1));
        Robot robot = robotFor(scenario);
        when(scenarioRepository.findActiveWalksForUpdate(anyCollection()))
            .thenReturn(List.of(scenario));
        when(robotRepository.findByIdForUpdate(scenario.getRobotId()))
            .thenReturn(Optional.of(robot));

        watchdog().tick();

        assertTimedOut(scenario, robot);
        assertThat(publisher.commands).singleElement()
            .extracting(RobotCommand::commandId)
            .isEqualTo("cmd-stop-fresh");
    }

    @Test
    void normalFollowingPastGenericTwentyMinutesRemainsActiveUntilWalkMaxDuration() {
        Scenario scenario = followingWalk(NOW.minusMinutes(21), NOW.minusMinutes(20));
        when(scenarioRepository.findActiveWalksForUpdate(anyCollection()))
            .thenReturn(List.of(scenario));

        watchdog().tick();

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FOLLOWING);
        assertThat(publisher.commands).isEmpty();
        verify(scenarioRepository, never()).save(scenario);
        verify(robotRepository, never()).findByIdForUpdate(scenario.getRobotId());
    }

    private Scenario startingWalk(OffsetDateTime requestedAt) {
        UUID robotId = UUID.randomUUID();
        Scenario scenario = Scenario.create(
            UUID.randomUUID(), robotId, ScenarioType.WALK, "walk-" + UUID.randomUUID());
        ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
        scenario.beginFollowStart("cmd-start-" + UUID.randomUUID(), requestedAt);
        return scenario;
    }

    private Scenario followingWalk(OffsetDateTime requestedAt, OffsetDateTime confirmedAt) {
        Scenario scenario = startingWalk(requestedAt);
        scenario.confirmFollowing(
            "evt-started-" + UUID.randomUUID(),
            scenario.getFollowStartCommandId(),
            "STARTED",
            null,
            confirmedAt,
            confirmedAt);
        return scenario;
    }

    private Robot robotFor(Scenario scenario) {
        Robot robot = Robot.create(scenario.getSeniorId(), "robot-" + UUID.randomUUID());
        ReflectionTestUtils.setField(robot, "id", scenario.getRobotId());
        robot.changeMode(RobotMode.SCENARIO_ACTIVE);
        return robot;
    }

    private void assertTimedOut(Scenario scenario, Robot robot) {
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.TIMED_OUT);
        assertThat(scenario.getCompletionResultCode()).isEqualTo("UNCHANGED");
        assertThat(scenario.getCompletionReasonCode()).isEqualTo("EXECUTION_TIMEOUT");
        assertThat(scenario.getLastFollowReasonCode()).isEqualTo("EXECUTION_TIMEOUT");
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
        verify(scenarioRepository).save(scenario);
        verify(robotRepository).save(robot);
    }

    private static final class RecordingPublisher implements RobotCommandPublisher {
        private final List<RobotCommand> commands = new ArrayList<>();

        @Override
        public void publish(RobotCommand command) {
            commands.add(command);
        }
    }
}
