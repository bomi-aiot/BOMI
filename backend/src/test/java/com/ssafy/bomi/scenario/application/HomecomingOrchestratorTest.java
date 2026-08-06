package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.conversation.domain.ConversationOutcome;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

class HomecomingOrchestratorTest {

    private static final String ENTRANCE_COMMAND_ID = "navigate-entrance";
    private static final String LIVING_ROOM_COMMAND_ID = "navigate-living-room";
    private static final String DEFAULT_COMMAND_ID = "navigate-default";

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final AppUserRepository appUserRepository = mock(AppUserRepository.class);
    private final ConversationRepository conversationRepository = mock(ConversationRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final RobotCommandPublisher commandPublisher = mock(RobotCommandPublisher.class);
    private final ConversationGateway conversationGateway = mock(ConversationGateway.class);
    private final HomecomingProperties properties = new HomecomingProperties();
    private final Clock clock = Clock.fixed(
        Instant.parse("2026-08-05T01:00:00Z"), ZoneOffset.UTC);

    private HomecomingOrchestrator orchestrator;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID robotUuid = UUID.randomUUID();
    private final String sensorId = "door-sensor-01";
    private final String deviceId = "robot-01";

    @BeforeEach
    void setUp() {
        properties.setSensorToSenior(Map.of(sensorId, seniorId));
        orchestrator = new HomecomingOrchestrator(
            scenarioRepository,
            conversationRepository,
            robotRepository,
            commandPublisher,
            conversationGateway,
            properties,
            new ScenarioRobotStartPolicy(
                new ScenarioStartGuard(scenarioRepository, appUserRepository),
                robotRepository,
                scenarioRepository),
            clock);
        when(appUserRepository.findByIdForUpdate(any()))
            .thenReturn(Optional.of(mock(AppUser.class)));
        when(scenarioRepository.save(any(Scenario.class))).thenAnswer(invocation -> {
            Scenario scenario = invocation.getArgument(0);
            if (scenario.getId() == null) {
                ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
            }
            return scenario;
        });
        when(conversationGateway.startConversation(any(UUID.class)))
            .thenReturn(ConversationStartResult.published(UUID.randomUUID()));
    }

    @Test
    void missingRobotIsDroppedWithoutThrowing() {
        when(robotRepository.findBySeniorIdForUpdate(seniorId)).thenReturn(Optional.empty());

        orchestrator.startHomecoming(sensorId);

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void activeScenarioSuppressesNewHomecoming() {
        when(robotRepository.findBySeniorIdForUpdate(seniorId))
            .thenReturn(Optional.of(robot()));
        when(scenarioRepository.existsBySeniorIdAndFinalStatusIn(eq(seniorId), anyCollection()))
            .thenReturn(true);

        orchestrator.startHomecoming(sensorId);

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void safeStopSuppressesHomecomingWithoutScenarioOrCommand() {
        Robot robot = robot();
        robot.changeMode(RobotMode.SAFE_STOP);
        when(robotRepository.findBySeniorIdForUpdate(seniorId))
            .thenReturn(Optional.of(robot));

        orchestrator.startHomecoming(sensorId);

        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void startHomecomingFromUnmappedSensorIsDroppedWithoutThrowing() {
        orchestrator.startHomecoming("unmapped-sensor");

        verifyNoInteractions(scenarioRepository);
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void startStoresConversationRequestAndOnlyNavigatesToEntrance() {
        when(robotRepository.findBySeniorIdForUpdate(seniorId))
            .thenReturn(Optional.of(robot()));

        orchestrator.startHomecoming(sensorId);

        ArgumentCaptor<Scenario> scenarioCaptor = ArgumentCaptor.forClass(Scenario.class);
        verify(scenarioRepository).save(scenarioCaptor.capture());
        Scenario saved = scenarioCaptor.getValue();
        assertThat(saved.getFinalStatus()).isEqualTo(ScenarioStatus.MOVING_TO_ENTRANCE);
        assertThat(saved.requirePreparedConversation().intent())
            .isEqualTo(ConversationIntent.HOMECOMING_GREETING);
        assertThat(saved.requirePreparedConversation().text()).isEqualTo(
            HomecomingOrchestrator.DEFAULT_GREETING);
        assertThat(saved.requirePreparedConversation().triggerContext())
            .containsEntry("sourceId", sensorId)
            .containsEntry("location", "ENTRANCE");

        ArgumentCaptor<RobotCommand> commandCaptor = ArgumentCaptor.forClass(RobotCommand.class);
        verify(commandPublisher).publish(commandCaptor.capture());
        assertThat(commandCaptor.getValue().type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(commandCaptor.getValue().payload()).containsEntry("target", "ENTRANCE");
    }

    @Test
    void arrivalRequestsAiAndWaitsForStartedEvent() {
        Scenario scenario = scenarioAt(ScenarioStatus.MOVING_TO_ENTRANCE);
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot()));

        orchestrator.onRobotArrived(scenario.getId(), deviceId);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.CHECKING_INTERACTION);
        verify(conversationGateway).startConversation(scenario.getId());
        verify(commandPublisher, never()).publish(any());
    }

    @ParameterizedTest
    @EnumSource(
        value = ScenarioType.class,
        names = {"WELLNESS_CHECK", "MEDICATION_REMINDER"}
    )
    void livingRoomScenarioArrivalAlsoRequestsAi(ScenarioType scenarioType) {
        ConversationIntent intent = scenarioType == ScenarioType.WELLNESS_CHECK
            ? ConversationIntent.WELLNESS_CHECK
            : ConversationIntent.MEDICATION_REMINDER;
        Scenario scenario = Scenario.create(
            seniorId, robotUuid, scenarioType, "external-event-01");
        scenario.prepareConversation(
            intent,
            "어르신, 확인할 시간이에요.",
            Map.of("location", "LIVING_ROOM"));
        scenario.beginMovingToEntrance();
        scenario.expectNavigationResult(LIVING_ROOM_COMMAND_ID, "LIVING_ROOM");
        ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot()));

        orchestrator.onRobotArrived(
            scenario.getId(), deviceId, LIVING_ROOM_COMMAND_ID, false);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.CHECKING_INTERACTION);
        assertThat(scenario.getActiveNavigationCommandId()).isNull();
        verify(conversationGateway).startConversation(scenario.getId());
        verify(commandPublisher, never()).publish(any());
    }

    @Test
    void immediateAiPublishFailureReturnsToDefault() {
        Scenario scenario = scenarioAt(ScenarioStatus.MOVING_TO_ENTRANCE);
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot()));
        when(conversationGateway.startConversation(scenario.getId()))
            .thenReturn(ConversationStartResult.failed(
                UUID.randomUUID(), MqttConversationGateway.REASON_AI_COMMAND_PUBLISH_FAILED));

        orchestrator.onRobotArrived(scenario.getId(), deviceId);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        ArgumentCaptor<RobotCommand> commandCaptor = ArgumentCaptor.forClass(RobotCommand.class);
        verify(commandPublisher).publish(commandCaptor.capture());
        assertThat(commandCaptor.getValue().payload()).containsEntry("target", "DEFAULT");
    }

    @Test
    void startedEventMovesScenarioToConversing() {
        Scenario scenario = scenarioAt(ScenarioStatus.CHECKING_INTERACTION);
        Conversation conversation = requestedConversation(scenario, false);
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot()));
        when(conversationRepository.findByIdForUpdate(conversation.getId()))
            .thenReturn(Optional.of(conversation));

        OffsetDateTime startedAt = OffsetDateTime.now(clock).plusSeconds(1);
        orchestrator.onConversationStarted(
            scenario.getId(), conversation.getId(), conversation.getStartCommandId(), deviceId,
            ConversationIntent.HOMECOMING_GREETING, startedAt);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.CONVERSING);
        assertThat(conversation.getAiStartedAt()).isEqualTo(startedAt);
    }

    @Test
    void staleNavigationCommandCannotCompleteCurrentReturn() {
        Scenario scenario = scenarioAt(ScenarioStatus.RETURNING_TO_DEFAULT);
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot()));

        assertThatThrownBy(() -> orchestrator.onRobotArrived(
            scenario.getId(), deviceId, ENTRANCE_COMMAND_ID, false))
            .isInstanceOf(com.ssafy.bomi.mqtt.inbound.MqttContractViolationException.class)
            .hasMessageContaining("commandId does not match");

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        assertThat(scenario.getActiveNavigationCommandId()).isEqualTo(DEFAULT_COMMAND_ID);
    }

    @Test
    void endedEventStoresOutcomeAndPublishesDefaultOnlyOnce() {
        Scenario scenario = scenarioAt(ScenarioStatus.CONVERSING);
        Conversation conversation = requestedConversation(scenario, true);
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot()));
        when(conversationRepository.findByIdForUpdate(conversation.getId()))
            .thenReturn(Optional.of(conversation));

        OffsetDateTime endedAt = OffsetDateTime.now(clock).plusMinutes(1);
        orchestrator.onConversationEnded(
            scenario.getId(), conversation.getId(), deviceId,
            ConversationOutcome.COMPLETED, null, endedAt);
        orchestrator.onConversationEnded(
            scenario.getId(), conversation.getId(), deviceId,
            ConversationOutcome.COMPLETED, null, endedAt);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        assertThat(conversation.getEndOutcome()).isEqualTo(ConversationOutcome.COMPLETED);
        verify(commandPublisher, times(1)).publish(any());
    }

    @Test
    void conversationEndDoesNotPublishReturnOrClearExternalSafeStop() {
        Scenario scenario = scenarioAt(ScenarioStatus.CONVERSING);
        Conversation conversation = requestedConversation(scenario, true);
        Robot robot = robot();
        robot.changeMode(RobotMode.SAFE_STOP);
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot));
        when(conversationRepository.findByIdForUpdate(conversation.getId()))
            .thenReturn(Optional.of(conversation));

        orchestrator.onConversationEnded(
            scenario.getId(), conversation.getId(), deviceId,
            ConversationOutcome.COMPLETED, null, OffsetDateTime.now(clock));

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FAILED);
        assertThat(scenario.getCompletionReasonCode()).isEqualTo("SAFETY_STOP");
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
        verify(commandPublisher, never()).publish(any());
    }

    @Test
    void successfulReturnAfterAiFailureRecordsFailureButLeavesRobotIdle() {
        Scenario scenario = scenarioAt(ScenarioStatus.RETURNING_TO_DEFAULT);
        Conversation conversation = requestedConversation(scenario, true);
        conversation.end(ConversationOutcome.FAILED, "AI_PROVIDER_ERROR",
            OffsetDateTime.now(clock));
        Robot robot = robot();
        robot.changeMode(RobotMode.SCENARIO_ACTIVE);
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot));
        when(conversationRepository.findByScenarioId(scenario.getId()))
            .thenReturn(Optional.of(conversation));

        orchestrator.onRobotArrived(scenario.getId(), deviceId);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FAILED);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
    }

    @Test
    void startTimeoutReturnsToDefaultThenFinishesTimedOutAndIdle() {
        Scenario scenario = scenarioAt(ScenarioStatus.CHECKING_INTERACTION);
        Conversation conversation = requestedConversation(scenario, false);
        Robot robot = robot();
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot));
        when(conversationRepository.findScenarioIdById(conversation.getId()))
            .thenReturn(Optional.of(scenario.getId()));
        when(conversationRepository.findByIdForUpdate(conversation.getId()))
            .thenReturn(Optional.of(conversation));
        when(conversationRepository.findByScenarioId(scenario.getId()))
            .thenReturn(Optional.of(conversation));

        orchestrator.onConversationStartTimedOut(conversation.getId());

        assertThat(conversation.getReasonCode())
            .isEqualTo(HomecomingOrchestrator.REASON_AI_START_TIMEOUT);
        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);

        orchestrator.onRobotArrived(scenario.getId(), deviceId);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.TIMED_OUT);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.IDLE);
    }

    @Test
    void navigationFailureUsesSafeStop() {
        Scenario scenario = scenarioAt(ScenarioStatus.RETURNING_TO_DEFAULT);
        Robot robot = robot();
        when(scenarioRepository.findByIdForUpdate(scenario.getId()))
            .thenReturn(Optional.of(scenario));
        when(robotRepository.findByIdForUpdate(robotUuid)).thenReturn(Optional.of(robot));

        orchestrator.onNavigationFailed(scenario.getId(), deviceId);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.FAILED);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
    }

    private Robot robot() {
        Robot robot = Robot.create(seniorId, deviceId);
        ReflectionTestUtils.setField(robot, "id", robotUuid);
        return robot;
    }

    private Scenario scenarioAt(ScenarioStatus status) {
        Scenario scenario = Scenario.create(seniorId, robotUuid, ScenarioType.HOMECOMING, sensorId);
        scenario.prepareConversation(
            ConversationIntent.HOMECOMING_GREETING,
            HomecomingOrchestrator.DEFAULT_GREETING,
            Map.of("sourceId", sensorId, "location", "ENTRANCE"));
        if (status != ScenarioStatus.RECEIVED) {
            scenario.beginMovingToEntrance();
            if (status == ScenarioStatus.MOVING_TO_ENTRANCE) {
                scenario.expectNavigationResult(ENTRANCE_COMMAND_ID, "ENTRANCE");
            }
        }
        if (status == ScenarioStatus.CHECKING_INTERACTION
            || status == ScenarioStatus.CONVERSING
            || status == ScenarioStatus.RETURNING_TO_DEFAULT) {
            scenario.checkInteraction();
        }
        if (status == ScenarioStatus.CONVERSING || status == ScenarioStatus.RETURNING_TO_DEFAULT) {
            scenario.beginConversation();
        }
        if (status == ScenarioStatus.RETURNING_TO_DEFAULT) {
            scenario.decideReturn();
            scenario.returnToDefault();
            scenario.expectNavigationResult(DEFAULT_COMMAND_ID, "DEFAULT");
        }
        ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
        return scenario;
    }

    private Conversation requestedConversation(Scenario scenario, boolean started) {
        Conversation conversation = Conversation.requestForScenario(
            seniorId, scenario.getId(), "command-01", OffsetDateTime.now(clock));
        ReflectionTestUtils.setField(conversation, "id", UUID.randomUUID());
        if (started) {
            conversation.markAiStarted(OffsetDateTime.now(clock).plusSeconds(1));
        }
        return conversation;
    }
}
