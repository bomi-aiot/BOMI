package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
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
import com.ssafy.bomi.robot.repository.RobotRepository.LockCandidate;
import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationAudit;
import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationDisposition;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.repository.OperatorScenarioCancellationAuditRepository;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OperatorScenarioCancellationServiceTest {

    @Mock RobotRepository robotRepository;
    @Mock ScenarioRepository scenarioRepository;
    @Mock ScenarioStartGuard scenarioStartGuard;
    @Mock OperatorScenarioCancellationAuditRepository auditRepository;
    @Mock RobotCommandPublisher publisher;

    private final UUID robotId = UUID.randomUUID();
    private final UUID seniorId = UUID.randomUUID();
    private final UUID scenarioId = UUID.randomUUID();
    private Robot robot;
    private Scenario scenario;
    private OperatorScenarioCancellationService service;

    @BeforeEach
    void setUp() {
        service = new OperatorScenarioCancellationService(
            robotRepository, scenarioRepository, scenarioStartGuard, auditRepository,
            List.of(publisher),
            Clock.fixed(Instant.parse("2026-08-08T00:00:00Z"), ZoneOffset.UTC));
        LockCandidate candidate = mock(LockCandidate.class);
        when(candidate.getId()).thenReturn(robotId);
        when(candidate.getSeniorId()).thenReturn(seniorId);
        when(robotRepository.findLockCandidateByDeviceId("bomi-AA001"))
            .thenReturn(Optional.of(candidate));
        when(scenarioStartGuard.lockSenior(seniorId)).thenReturn(true);

        robot = mock(Robot.class);
        when(robot.getId()).thenReturn(robotId);
        when(robot.getDeviceId()).thenReturn("bomi-AA001");
        when(robot.getSeniorId()).thenReturn(seniorId);
        when(robot.isActive()).thenReturn(true);
        when(robot.getCurrentMode()).thenReturn(RobotMode.SCENARIO_ACTIVE);
        when(robotRepository.findByIdForUpdate(robotId)).thenReturn(Optional.of(robot));

        scenario = mock(Scenario.class);
        when(scenario.getId()).thenReturn(scenarioId);
        when(scenario.getFinalStatus()).thenReturn(ScenarioStatus.MOVING_TO_ENTRANCE);
        when(scenario.getActiveNavigationCommandId()).thenReturn("navigate-01");
        when(scenarioRepository.findActiveByRobotIdForUpdate(any(), anyCollection()))
            .thenReturn(List.of(scenario));
        when(auditRepository.save(any(OperatorScenarioCancellationAudit.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));
    }

    @Test
    void cancelsNavigationMovesRobotToSafeStopAndPublishesCancel() {
        OperatorScenarioCancellationResult result = service.cancelActiveNavigation(
            "bomi-AA001", "operator-a", true, "robot inspected");

        assertThat(result.disposition())
            .isEqualTo(OperatorScenarioCancellationDisposition.CANCELLED);
        assertThat(result.currentScenarioStatus()).isEqualTo(ScenarioStatus.CANCELLED);
        assertThat(result.currentMode()).isEqualTo(RobotMode.SAFE_STOP);
        verify(scenario).cancel("CANCELLED", "OPERATOR_CANCELLED");
        verify(robot).changeMode(RobotMode.SAFE_STOP);
        verify(auditRepository).save(any(OperatorScenarioCancellationAudit.class));

        ArgumentCaptor<RobotCommand> command = ArgumentCaptor.forClass(RobotCommand.class);
        verify(publisher).publish(command.capture());
        assertThat(command.getValue().type()).isEqualTo(RobotCommandType.CANCEL);
        assertThat(command.getValue().scenarioId()).isEqualTo(scenarioId);
        assertThat(command.getValue().payload())
            .containsEntry("targetCommandId", "navigate-01")
            .containsEntry("reasonCode", "OPERATOR_CANCELLED");
    }

    @Test
    void repeatedRequestWithoutActiveScenarioIsIdempotentNoOp() {
        when(scenarioRepository.findActiveByRobotIdForUpdate(any(), anyCollection()))
            .thenReturn(List.of());

        OperatorScenarioCancellationResult result = service.cancelActiveNavigation(
            "bomi-AA001", "operator-a", true, "already cancelled check");

        assertThat(result.disposition())
            .isEqualTo(OperatorScenarioCancellationDisposition.NO_OP_NO_ACTIVE_SCENARIO);
        verify(robot, never()).changeMode(any());
        verify(publisher, never()).publish(any());
        verify(auditRepository, never()).save(any());
    }

    @Test
    void activeNonNavigationScenarioIsCancelledWithoutMqttCommand() {
        when(scenario.getActiveNavigationCommandId()).thenReturn(null);

        OperatorScenarioCancellationResult result = service.cancelActiveNavigation(
            "bomi-AA001", "operator-a", true, "inspect non-navigation flow");

        assertThat(result.disposition())
            .isEqualTo(OperatorScenarioCancellationDisposition.CANCELLED);
        assertThat(result.cancelCommandId()).isNull();
        verify(scenario).cancel("CANCELLED", "OPERATOR_CANCELLED");
        verify(robot).changeMode(RobotMode.SAFE_STOP);
        verify(auditRepository).save(any(OperatorScenarioCancellationAudit.class));
        verify(publisher, never()).publish(any());
    }

    @Test
    void physicalSafetyConfirmationIsRequiredBeforeLocking() {
        assertThatThrownBy(() -> service.cancelActiveNavigation(
            "bomi-AA001", "operator-a", false, "not inspected"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("physicalSafetyConfirmed");
        verify(robotRepository, never()).findLockCandidateByDeviceId(any());
    }
}
