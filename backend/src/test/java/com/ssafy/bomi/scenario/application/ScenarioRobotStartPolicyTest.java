package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class ScenarioRobotStartPolicyTest {

    private final ScenarioStartGuard startGuard = mock(ScenarioStartGuard.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final ScenarioRobotStartPolicy policy = new ScenarioRobotStartPolicy(
        startGuard, robotRepository, scenarioRepository);

    private final UUID seniorId = UUID.randomUUID();
    private final UUID robotId = UUID.randomUUID();
    private final String deviceId = "bomi-policy-01";
    private Robot robot;

    @BeforeEach
    void setUp() {
        robot = Robot.create(seniorId, deviceId);
        ReflectionTestUtils.setField(robot, "id", robotId);
        when(startGuard.check(eq(seniorId), eq(ScenarioType.HOMECOMING), eq(Duration.ZERO)))
            .thenReturn(Optional.empty());
        when(robotRepository.findBySeniorIdForUpdate(seniorId)).thenReturn(Optional.of(robot));
    }

    @Test
    void safeStopIsNeverAdmittedForMovement() {
        robot.changeMode(RobotMode.SAFE_STOP);

        var decision = admitHomecoming();

        assertThat(decision.blockReason())
            .isEqualTo(ScenarioRobotStartPolicy.BlockReason.SAFE_STOP);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
    }

    @Test
    void inactiveUnregisteredAndUnassignedRobotsAreRejected() {
        robot.deactivate();
        assertThat(admitHomecoming().blockReason())
            .isEqualTo(ScenarioRobotStartPolicy.BlockReason.INACTIVE_ROBOT);

        Robot unregistered = Robot.create(seniorId);
        ReflectionTestUtils.setField(unregistered, "id", UUID.randomUUID());
        when(robotRepository.findBySeniorIdForUpdate(seniorId))
            .thenReturn(Optional.of(unregistered));
        assertThat(admitHomecoming().blockReason())
            .isEqualTo(ScenarioRobotStartPolicy.BlockReason.UNREGISTERED_ROBOT);

        Robot unassigned = Robot.create(null, "bomi-unassigned");
        ReflectionTestUtils.setField(unassigned, "id", UUID.randomUUID());
        RobotRepository.LockCandidate unassignedCandidate =
            mock(RobotRepository.LockCandidate.class);
        when(robotRepository.findLockCandidateByDeviceId("bomi-unassigned"))
            .thenReturn(Optional.of(unassignedCandidate));
        assertThat(policy.admitByDevice(
            "bomi-unassigned",
            ScenarioType.WALK,
            Duration.ZERO,
            ScenarioRobotStartPolicy.ModePolicy.IDLE_ONLY).blockReason())
            .isEqualTo(ScenarioRobotStartPolicy.BlockReason.UNASSIGNED_ROBOT);
    }

    @Test
    void activeScenarioAndStaleBusyModeAreRejected() {
        when(startGuard.check(eq(seniorId), eq(ScenarioType.HOMECOMING), eq(Duration.ZERO)))
            .thenReturn(Optional.of(ScenarioStartGuard.BlockReason.ACTIVE_SCENARIO_EXISTS));
        assertThat(admitHomecoming().blockReason())
            .isEqualTo(ScenarioRobotStartPolicy.BlockReason.ACTIVE_SCENARIO_EXISTS);

        when(startGuard.check(eq(seniorId), eq(ScenarioType.HOMECOMING), eq(Duration.ZERO)))
            .thenReturn(Optional.empty());
        robot.changeMode(RobotMode.SCENARIO_ACTIVE);
        assertThat(admitHomecoming().blockReason())
            .isEqualTo(ScenarioRobotStartPolicy.BlockReason.BUSY_MODE);
    }

    @Test
    void robotScopedActiveScenarioIsAlsoRejected() {
        when(scenarioRepository.existsByRobotIdAndFinalStatusIn(eq(robotId), anyCollection()))
            .thenReturn(true);

        assertThat(admitHomecoming().blockReason())
            .isEqualTo(ScenarioRobotStartPolicy.BlockReason.ACTIVE_SCENARIO_EXISTS);
    }

    @Test
    void onlyWakeWordPolicyAllowsRestGuard() {
        robot.changeMode(RobotMode.REST_GUARD);
        RobotRepository.LockCandidate candidate = mock(RobotRepository.LockCandidate.class);
        when(candidate.getSeniorId()).thenReturn(seniorId);
        when(robotRepository.findLockCandidateByDeviceId(deviceId))
            .thenReturn(Optional.of(candidate));
        when(robotRepository.findByDeviceIdForUpdate(deviceId)).thenReturn(Optional.of(robot));
        when(startGuard.check(eq(seniorId), eq(ScenarioType.WAKE_WORD_CALL), eq(Duration.ZERO)))
            .thenReturn(Optional.empty());

        assertThat(policy.admitByDevice(
            deviceId,
            ScenarioType.WAKE_WORD_CALL,
            Duration.ZERO,
            ScenarioRobotStartPolicy.ModePolicy.IDLE_OR_REST_GUARD).allowed()).isTrue();
        assertThat(admitHomecoming().blockReason())
            .isEqualTo(ScenarioRobotStartPolicy.BlockReason.REST_GUARD);
    }

    private ScenarioRobotStartPolicy.Decision admitHomecoming() {
        return policy.admitBySenior(
            seniorId,
            ScenarioType.HOMECOMING,
            Duration.ZERO,
            ScenarioRobotStartPolicy.ModePolicy.IDLE_ONLY);
    }
}
