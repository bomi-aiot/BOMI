package com.ssafy.bomi.robot.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryAudit;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryDisposition;
import com.ssafy.bomi.robot.repository.RobotModeRecoveryAuditRepository;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.robot.repository.RobotRepository.LockCandidate;
import com.ssafy.bomi.scenario.application.ScenarioStartGuard;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.mockito.junit.jupiter.MockitoSettings;
import org.mockito.quality.Strictness;

@ExtendWith(MockitoExtension.class)
@MockitoSettings(strictness = Strictness.LENIENT)
class RobotModeRecoveryServiceTest {

    private static final String DEVICE_ID = "bomi-AA001";
    private static final String OPERATOR_ID = "operator-a";
    private static final OffsetDateTime NOW =
        OffsetDateTime.parse("2026-08-05T12:00:00Z");

    @Mock private RobotRepository robotRepository;
    @Mock private ScenarioRepository scenarioRepository;
    @Mock private ScenarioStartGuard scenarioStartGuard;
    @Mock private RobotModeRecoveryAuditRepository auditRepository;

    private final UUID robotId = UUID.randomUUID();
    private final UUID seniorId = UUID.randomUUID();
    private Robot robot;
    private RobotModeRecoveryService service;

    @BeforeEach
    void setUp() {
        Clock clock = Clock.fixed(Instant.parse("2026-08-05T12:00:00Z"), ZoneOffset.UTC);
        service = new RobotModeRecoveryService(
            robotRepository, scenarioRepository, scenarioStartGuard, auditRepository, clock);

        LockCandidate candidate = mock(LockCandidate.class);
        when(candidate.getId()).thenReturn(robotId);
        when(candidate.getSeniorId()).thenReturn(seniorId);
        when(robotRepository.findLockCandidateByDeviceId(DEVICE_ID))
            .thenReturn(Optional.of(candidate));
        when(scenarioStartGuard.lockSenior(seniorId)).thenReturn(true);

        robot = mock(Robot.class);
        when(robot.getId()).thenReturn(robotId);
        when(robot.getDeviceId()).thenReturn(DEVICE_ID);
        when(robot.getSeniorId()).thenReturn(seniorId);
        when(robot.isActive()).thenReturn(true);
        when(robotRepository.findByIdForUpdate(robotId)).thenReturn(Optional.of(robot));
        when(auditRepository.save(any(RobotModeRecoveryAudit.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));
    }

    @Test
    void safeStopWithoutActiveScenarioRecoversToIdleAndAudits() {
        when(robot.getCurrentMode()).thenReturn(RobotMode.SAFE_STOP);

        RobotModeRecoveryResult result = service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, true, "physical inspection completed");

        assertThat(result.disposition()).isEqualTo(RobotModeRecoveryDisposition.RECOVERED);
        assertThat(result.previousMode()).isEqualTo(RobotMode.SAFE_STOP);
        assertThat(result.currentMode()).isEqualTo(RobotMode.IDLE);
        assertThat(result.recoveredAt()).isEqualTo(NOW);
        verify(robot).changeMode(RobotMode.IDLE);

        ArgumentCaptor<RobotModeRecoveryAudit> audit =
            ArgumentCaptor.forClass(RobotModeRecoveryAudit.class);
        verify(auditRepository).save(audit.capture());
        assertThat(audit.getValue().getOperatorId()).isEqualTo(OPERATOR_ID);
        assertThat(audit.getValue().getPreviousMode()).isEqualTo(RobotMode.SAFE_STOP);
        assertThat(audit.getValue().getTargetMode()).isEqualTo(RobotMode.IDLE);
        assertThat(audit.getValue().getReason()).isEqualTo("physical inspection completed");
        assertThat(audit.getValue().getRecoveredAt()).isEqualTo(NOW);
    }

    @Test
    void staleScenarioActiveWithoutActiveScenarioRecoversToIdle() {
        when(robot.getCurrentMode()).thenReturn(RobotMode.SCENARIO_ACTIVE);

        RobotModeRecoveryResult result = service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, true, "stale scenario mode verified");

        assertThat(result.disposition()).isEqualTo(RobotModeRecoveryDisposition.RECOVERED);
        assertThat(result.previousMode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(result.currentMode()).isEqualTo(RobotMode.IDLE);
        verify(robot).changeMode(RobotMode.IDLE);
        verify(auditRepository).save(any(RobotModeRecoveryAudit.class));
    }

    @Test
    void alreadyIdleIsAuditedAsIdempotentNoOp() {
        when(robot.getCurrentMode()).thenReturn(RobotMode.IDLE);

        RobotModeRecoveryResult result = service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, true, "verified stale alert");

        assertThat(result.disposition())
            .isEqualTo(RobotModeRecoveryDisposition.NO_OP_ALREADY_IDLE);
        verify(robot, never()).changeMode(any());
        verify(auditRepository).save(any(RobotModeRecoveryAudit.class));
    }

    @Test
    void activeScenarioRejectsRecoveryBeforeModeOrAuditMutation() {
        when(robot.getCurrentMode()).thenReturn(RobotMode.SAFE_STOP);
        when(scenarioRepository.existsBySeniorIdAndFinalStatusIn(
            eq(seniorId), anyCollection())).thenReturn(true);

        RobotModeRecoveryResult result = service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, true, "physical inspection completed");

        assertThat(result.disposition())
            .isEqualTo(RobotModeRecoveryDisposition.REJECTED_ACTIVE_SCENARIO);
        verify(robot, never()).changeMode(any());
        verify(auditRepository, never()).save(any());
    }

    @Test
    void restGuardIsNotRecoverable() {
        when(robot.getCurrentMode()).thenReturn(RobotMode.REST_GUARD);

        RobotModeRecoveryResult result = service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, true, "rest guard inspected");

        assertThat(result.disposition())
            .isEqualTo(RobotModeRecoveryDisposition.REJECTED_MODE_NOT_RECOVERABLE);
        assertThat(result.currentMode()).isEqualTo(RobotMode.REST_GUARD);
        verify(robot, never()).changeMode(any());
        verify(auditRepository, never()).save(any());
    }

    @Test
    void unknownRobotIsRejected() {
        when(robotRepository.findLockCandidateByDeviceId(DEVICE_ID))
            .thenReturn(Optional.empty());

        RobotModeRecoveryResult result = service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, true, "unknown robot check");

        assertThat(result.disposition())
            .isEqualTo(RobotModeRecoveryDisposition.REJECTED_UNKNOWN_ROBOT);
        verify(robotRepository, never()).findByIdForUpdate(any());
        verify(auditRepository, never()).save(any());
    }

    @Test
    void inactiveRobotIsRejectedAfterLockedRecheck() {
        when(robot.isActive()).thenReturn(false);
        when(robot.getCurrentMode()).thenReturn(RobotMode.SAFE_STOP);

        RobotModeRecoveryResult result = service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, true, "inactive robot check");

        assertThat(result.disposition())
            .isEqualTo(RobotModeRecoveryDisposition.REJECTED_INACTIVE_ROBOT);
        verify(robot, never()).changeMode(any());
        verify(auditRepository, never()).save(any());
    }

    @Test
    void unassignedRobotIsRejectedAfterLockedRecheck() {
        when(robot.getSeniorId()).thenReturn(null);
        when(robot.getCurrentMode()).thenReturn(RobotMode.SAFE_STOP);

        RobotModeRecoveryResult result = service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, true, "assignment check");

        assertThat(result.disposition())
            .isEqualTo(RobotModeRecoveryDisposition.REJECTED_UNASSIGNED_ROBOT);
        verify(robot, never()).changeMode(any());
        verify(auditRepository, never()).save(any());
    }

    @Test
    void physicalSafetyConfirmationIsEnforcedInApplicationLayer() {
        assertThatThrownBy(() -> service.recoverToIdle(
            DEVICE_ID, OPERATOR_ID, false, "not confirmed"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("physicalSafetyConfirmed");

        verify(robotRepository, never()).findLockCandidateByDeviceId(any());
    }

    @Test
    void recoveryServiceHasNoMqttDependency() {
        assertThat(Arrays.stream(RobotModeRecoveryService.class.getDeclaredFields())
            .map(field -> field.getType().getPackageName()))
            .noneMatch(packageName -> packageName.startsWith("com.ssafy.bomi.mqtt"));
    }
}
