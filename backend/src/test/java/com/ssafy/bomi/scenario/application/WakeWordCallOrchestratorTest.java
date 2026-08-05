package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.mqtt.inbound.MqttContractViolationException;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.application.ScenarioStartGuard.BlockReason;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.domain.WakeWordTriggerDisposition;
import com.ssafy.bomi.scenario.domain.WakeWordTriggerReceipt;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.scenario.repository.WakeWordTriggerReceiptRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

class WakeWordCallOrchestratorTest {

    private static final String DEVICE_ID = "robot-01";
    private static final String EVENT_ID = "wake-event-01";
    private static final String KEYWORD = "보미야";
    private static final double CONFIDENCE = 0.92;
    private static final OffsetDateTime OCCURRED_AT =
        OffsetDateTime.parse("2026-08-05T10:00:00+09:00");

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final WakeWordTriggerReceiptRepository receiptRepository =
        mock(WakeWordTriggerReceiptRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final RobotCommandPublisher commandPublisher = mock(RobotCommandPublisher.class);
    private final ScenarioStartGuard startGuard = mock(ScenarioStartGuard.class);
    private final Clock clock = Clock.fixed(
        Instant.parse("2026-08-05T01:00:00Z"), ZoneOffset.UTC);

    private final UUID seniorId = UUID.randomUUID();
    private final UUID robotId = UUID.randomUUID();
    private final UUID scenarioId = UUID.randomUUID();
    private final AtomicReference<WakeWordTriggerReceipt> receiptStore = new AtomicReference<>();
    private final AtomicReference<Scenario> scenarioStore = new AtomicReference<>();

    private Robot robot;
    private WakeWordCallOrchestrator orchestrator;

    @BeforeEach
    void setUp() {
        robot = Robot.create(seniorId, DEVICE_ID);
        ReflectionTestUtils.setField(robot, "id", robotId);
        when(robotRepository.findByDeviceId(DEVICE_ID)).thenReturn(Optional.of(robot));
        when(robotRepository.findByDeviceIdForUpdate(DEVICE_ID)).thenReturn(Optional.of(robot));
        when(robotRepository.findByIdForUpdate(robotId)).thenReturn(Optional.of(robot));
        when(startGuard.check(any(), any(), any())).thenReturn(Optional.empty());

        when(receiptRepository.findById(anyString()))
            .thenAnswer(invocation -> Optional.ofNullable(receiptStore.get()));
        when(receiptRepository.saveAndFlush(any(WakeWordTriggerReceipt.class)))
            .thenAnswer(invocation -> {
                WakeWordTriggerReceipt receipt = invocation.getArgument(0);
                receiptStore.set(receipt);
                return receipt;
            });
        when(scenarioRepository.save(any(Scenario.class))).thenAnswer(invocation -> {
            Scenario scenario = invocation.getArgument(0);
            ReflectionTestUtils.setField(scenario, "id", scenarioId);
            scenarioStore.set(scenario);
            return scenario;
        });
        when(scenarioRepository.saveAndFlush(any(Scenario.class)))
            .thenAnswer(invocation -> invocation.getArgument(0));
        when(scenarioRepository.findByIdForUpdate(scenarioId))
            .thenAnswer(invocation -> Optional.ofNullable(scenarioStore.get()));

        orchestrator = new WakeWordCallOrchestrator(
            scenarioRepository,
            receiptRepository,
            robotRepository,
            commandPublisher,
            startGuard,
            clock);
    }

    @Test
    void acceptedWakeWordPersistsMinimalContextAndPublishesOneLivingRoomNavigation() {
        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);

        Scenario scenario = scenarioStore.get();
        assertThat(scenario.getScenarioType()).isEqualTo(ScenarioType.WAKE_WORD_CALL);
        assertThat(scenario.getExternalEventId()).isEqualTo(EVENT_ID);
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.NAVIGATING);
        assertThat(scenario.getTriggerContext())
            .containsEntry("robotId", DEVICE_ID)
            .containsEntry("occurredAt", OCCURRED_AT.toString())
            .containsEntry("keyword", KEYWORD)
            .containsEntry("confidence", CONFIDENCE);
        assertThat(scenario.getConversationRequest()).isNull();

        RobotCommand command = publishedCommand();
        assertThat(command.type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(command.scenarioId()).isEqualTo(scenarioId);
        assertThat(command.robotId()).isEqualTo(DEVICE_ID);
        assertThat(command.payload()).hasSize(1).containsEntry("target", "LIVING_ROOM");
        assertThat(command.expiresAt()).isAfter(command.occurredAt());
        assertThat(scenario.getActiveNavigationCommandId()).isEqualTo(command.commandId());
        assertThat(scenario.getActiveNavigationTarget()).isEqualTo("LIVING_ROOM");
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(receiptStore.get().getDisposition())
            .isEqualTo(WakeWordTriggerDisposition.ACCEPTED);
        assertThat(receiptStore.get().getScenarioId()).isEqualTo(scenarioId);
    }

    @Test
    void arrivedCompletesImmediatelyWithoutPublishingReturnCommand() {
        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);
        RobotCommand command = publishedCommand();

        orchestrator.onNavigationResult(
            scenarioId, DEVICE_ID, command.commandId(), false,
            "SUCCEEDED", "ARRIVED", null);

        Scenario scenario = scenarioStore.get();
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(scenario.getCompletionResultCode()).isEqualTo("ARRIVED");
        assertThat(scenario.getCompletionReasonCode()).isNull();
        assertThat(scenario.getActiveNavigationCommandId()).isNull();
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
        verify(commandPublisher, times(1)).publish(any());
    }

    @ParameterizedTest
    @CsvSource({
        "FAILED,FAILED,PATH_BLOCKED",
        "CANCELLED,CANCELLED,SAFETY_STOP",
        "TIMED_OUT,TIMED_OUT,EXECUTION_TIMEOUT"
    })
    void exceptionalNavigationOutcomeMapsToSameTerminalStatusAndSafeStop(
        String outcome,
        ScenarioStatus expected,
        String reasonCode
    ) {
        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);
        RobotCommand command = publishedCommand();

        orchestrator.onNavigationResult(
            scenarioId, DEVICE_ID, command.commandId(), false,
            outcome, "NOT_ARRIVED", reasonCode);

        assertThat(scenarioStore.get().getFinalStatus()).isEqualTo(expected);
        assertThat(scenarioStore.get().getCompletionResultCode()).isEqualTo("NOT_ARRIVED");
        assertThat(scenarioStore.get().getCompletionReasonCode()).isEqualTo(reasonCode);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
        verify(commandPublisher, times(1)).publish(any());
    }

    @Test
    void restGuardIsAllowedAndPreservedAfterSuccessfulArrival() {
        robot.changeMode(RobotMode.REST_GUARD);

        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);
        RobotCommand command = publishedCommand();
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.REST_GUARD);

        orchestrator.onNavigationResult(
            scenarioId, DEVICE_ID, command.commandId(), false,
            "SUCCEEDED", "ARRIVED", null);

        assertThat(scenarioStore.get().getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.REST_GUARD);
    }

    @Test
    void legacyNavigationResultIsRejectedWithoutChangingWakeScenario() {
        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);
        RobotCommand command = publishedCommand();

        assertThatThrownBy(() -> orchestrator.onNavigationResult(
            scenarioId, DEVICE_ID, command.commandId(), true,
            "SUCCEEDED", "ARRIVED", null))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("requires v1");

        assertThat(scenarioStore.get().getFinalStatus()).isEqualTo(ScenarioStatus.NAVIGATING);
    }

    @Test
    void safeStopRejectsAndDurablyRemembersTheEvent() {
        robot.changeMode(RobotMode.SAFE_STOP);

        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);
        robot.changeMode(RobotMode.IDLE);
        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);

        assertThat(receiptStore.get().getDisposition())
            .isEqualTo(WakeWordTriggerDisposition.REJECTED_SAFE_STOP);
        verify(scenarioRepository, never()).save(any());
        verify(commandPublisher, never()).publish(any());
    }

    @Test
    void unknownInactiveAndUnassignedRobotsAreRejectedWithoutCommands() {
        when(robotRepository.findByDeviceId(DEVICE_ID)).thenReturn(Optional.empty());
        when(robotRepository.findByDeviceIdForUpdate(DEVICE_ID)).thenReturn(Optional.empty());
        orchestrator.onWakeWordDetected(
            DEVICE_ID, "unknown-event", OCCURRED_AT, KEYWORD, null);
        assertThat(receiptStore.get().getDisposition())
            .isEqualTo(WakeWordTriggerDisposition.REJECTED_UNKNOWN_ROBOT);

        resetDurableReceipt();
        when(robotRepository.findByDeviceId(DEVICE_ID)).thenReturn(Optional.of(robot));
        when(robotRepository.findByDeviceIdForUpdate(DEVICE_ID)).thenReturn(Optional.of(robot));
        robot.deactivate();
        orchestrator.onWakeWordDetected(
            DEVICE_ID, "inactive-event", OCCURRED_AT, KEYWORD, null);
        assertThat(receiptStore.get().getDisposition())
            .isEqualTo(WakeWordTriggerDisposition.REJECTED_INACTIVE_ROBOT);

        resetDurableReceipt();
        robot.activate();
        robot.unassignSenior();
        orchestrator.onWakeWordDetected(
            DEVICE_ID, "unassigned-event", OCCURRED_AT, KEYWORD, null);
        assertThat(receiptStore.get().getDisposition())
            .isEqualTo(WakeWordTriggerDisposition.REJECTED_UNASSIGNED_ROBOT);

        verify(scenarioRepository, never()).save(any());
        verify(commandPublisher, never()).publish(any());
    }

    @Test
    void anotherActiveScenarioSuppressesMovementAndDuplicateStaysRejected() {
        when(startGuard.check(any(), any(), any()))
            .thenReturn(Optional.of(BlockReason.ACTIVE_SCENARIO_EXISTS))
            .thenReturn(Optional.empty());

        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);
        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);

        assertThat(receiptStore.get().getDisposition())
            .isEqualTo(WakeWordTriggerDisposition.REJECTED_ACTIVE_SCENARIO);
        verify(startGuard, times(1)).check(any(), any(), any());
        verify(scenarioRepository, never()).save(any());
        verify(commandPublisher, never()).publish(any());
    }

    @Test
    void wrongRobotCommandOrStoredTargetCannotCorruptState() {
        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);
        RobotCommand command = publishedCommand();

        assertThatThrownBy(() -> orchestrator.onNavigationResult(
            scenarioId, "other-robot", command.commandId(), false,
            "SUCCEEDED", "ARRIVED", null))
            .isInstanceOf(MqttContractViolationException.class);
        assertThatThrownBy(() -> orchestrator.onNavigationResult(
            scenarioId, DEVICE_ID, "wrong-command", false,
            "SUCCEEDED", "ARRIVED", null))
            .isInstanceOf(MqttContractViolationException.class);
        ReflectionTestUtils.setField(
            scenarioStore.get(), "activeNavigationTarget", "ENTRANCE");
        assertThatThrownBy(() -> orchestrator.onNavigationResult(
            scenarioId, DEVICE_ID, command.commandId(), false,
            "SUCCEEDED", "ARRIVED", null))
            .isInstanceOf(MqttContractViolationException.class);

        assertThat(scenarioStore.get().getFinalStatus()).isEqualTo(ScenarioStatus.NAVIGATING);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
    }

    @Test
    void unknownAndLateDuplicateResultsAreNoOps() {
        assertThatCode(() -> orchestrator.onNavigationResult(
            UUID.randomUUID(), DEVICE_ID, "unknown", false,
            "SUCCEEDED", "ARRIVED", null)).doesNotThrowAnyException();

        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);
        RobotCommand command = publishedCommand();
        orchestrator.onNavigationResult(
            scenarioId, DEVICE_ID, command.commandId(), false,
            "SUCCEEDED", "ARRIVED", null);

        assertThatCode(() -> orchestrator.onNavigationResult(
            scenarioId, DEVICE_ID, command.commandId(), false,
            "SUCCEEDED", "ARRIVED", null)).doesNotThrowAnyException();
        assertThat(scenarioStore.get().getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        verify(commandPublisher, times(1)).publish(any());
    }

    @Test
    void reusedEventIdWithDifferentTriggerIsAContractViolation() {
        orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT, KEYWORD, CONFIDENCE);

        assertThatThrownBy(() -> orchestrator.onWakeWordDetected(
            DEVICE_ID, EVENT_ID, OCCURRED_AT.plusSeconds(1), KEYWORD, CONFIDENCE))
            .isInstanceOf(MqttContractViolationException.class);
        verify(commandPublisher, times(1)).publish(any());
    }

    private RobotCommand publishedCommand() {
        ArgumentCaptor<RobotCommand> captor = ArgumentCaptor.forClass(RobotCommand.class);
        verify(commandPublisher).publish(captor.capture());
        return captor.getValue();
    }

    private void resetDurableReceipt() {
        receiptStore.set(null);
    }
}
