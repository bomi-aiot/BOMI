package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.observation.config.ObservationProperties;
import com.ssafy.bomi.observation.config.WellnessProperties;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

class WellnessCheckOrchestratorTest {

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final AppUserRepository appUserRepository = mock(AppUserRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final RobotCommandPublisher commandPublisher = mock(RobotCommandPublisher.class);
    private final ObservationProperties observationProperties = new ObservationProperties();
    private final WellnessProperties wellnessProperties = new WellnessProperties();
    private final ObjectMapper objectMapper = new ObjectMapper();

    private WellnessCheckOrchestrator orchestrator;
    private Robot robot;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID robotUuid = UUID.randomUUID();
    private final String sensorId = "ambient-sensor-01";

    @BeforeEach
    void setUp() {
        observationProperties.setAmbientSensorToSenior(Map.of(sensorId, seniorId));
        orchestrator = new WellnessCheckOrchestrator(
            scenarioRepository, robotRepository, commandPublisher,
            new ScenarioRobotStartPolicy(
                new ScenarioStartGuard(scenarioRepository, appUserRepository),
                robotRepository,
                scenarioRepository),
            observationProperties, wellnessProperties);

        when(appUserRepository.findByIdForUpdate(any()))
            .thenReturn(Optional.of(mock(AppUser.class)));

        when(scenarioRepository.save(any(Scenario.class))).thenAnswer(invocation -> {
            Scenario s = invocation.getArgument(0);
            if (s.getId() == null) {
                ReflectionTestUtils.setField(s, "id", UUID.randomUUID());
            }
            return s;
        });
        robot = Robot.create(seniorId, "robot-01");
        ReflectionTestUtils.setField(robot, "id", robotUuid);
        when(robotRepository.findBySeniorIdForUpdate(seniorId)).thenReturn(Optional.of(robot));
    }

    private ObjectNode ambient(Double temp, Double humidity) {
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        if (temp != null) {
            payload.put("temperatureC", temp);
        }
        if (humidity != null) {
            payload.put("humidityPercent", humidity);
        }
        return body;
    }

    @Test
    void highTemperatureStoresConversationAndOnlyNavigates() {
        orchestrator.onAmbientObserved(sensorId, ambient(31.0, 50.0));

        ArgumentCaptor<Scenario> scenarioCaptor = ArgumentCaptor.forClass(Scenario.class);
        verify(scenarioRepository).save(scenarioCaptor.capture());
        Scenario scenario = scenarioCaptor.getValue();
        assertThat(scenario.getScenarioType()).isEqualTo(ScenarioType.WELLNESS_CHECK);
        assertThat(scenario.requirePreparedConversation().intent())
            .isEqualTo(ConversationIntent.WELLNESS_CHECK);
        assertThat(scenario.requirePreparedConversation().text())
            .isEqualTo(WellnessCheckOrchestrator.DEFAULT_PROMPT);
        assertThat(scenario.requirePreparedConversation().triggerContext())
            .containsEntry("sourceId", sensorId)
            .containsEntry("location", "LIVING_ROOM")
            .containsEntry("temperatureC", new java.math.BigDecimal("31.0"))
            .containsEntry("humidityPercent", new java.math.BigDecimal("50.0"));

        ArgumentCaptor<RobotCommand> commandCaptor = ArgumentCaptor.forClass(RobotCommand.class);
        verify(commandPublisher).publish(commandCaptor.capture());
        RobotCommand navigate = commandCaptor.getValue();
        assertThat(navigate.type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(navigate.payload()).containsEntry("target", "LIVING_ROOM");
        assertThat(scenario.getActiveNavigationCommandId())
            .isEqualTo(navigate.commandId());
    }

    @Test
    void highHumidityAloneAlsoTriggers() {
        orchestrator.onAmbientObserved(sensorId, ambient(24.0, 85.0));

        verify(scenarioRepository).save(any(Scenario.class));
    }

    @Test
    void temperatureAtThresholdTriggers() {
        orchestrator.onAmbientObserved(sensorId, ambient(30.0, 50.0));

        verify(scenarioRepository).save(any(Scenario.class));
    }

    @Test
    void humidityAtThresholdTriggers() {
        orchestrator.onAmbientObserved(sensorId, ambient(24.0, 80.0));

        verify(scenarioRepository).save(any(Scenario.class));
    }

    @Test
    void normalReadingDoesNothing() {
        orchestrator.onAmbientObserved(sensorId, ambient(24.0, 50.0));

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void readingsJustBelowThresholdDoNothing() {
        orchestrator.onAmbientObserved(sensorId, ambient(29.9, 79.9));

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void missingMeasurementsDoNothing() {
        // 측정값이 아예 없는 payload — null 은 임계값 비교에 참여하지 않는다.
        orchestrator.onAmbientObserved(sensorId, ambient(null, null));

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void activeScenarioSuppressesWellnessCheck() {
        when(scenarioRepository.existsBySeniorIdAndFinalStatusIn(eq(seniorId), anyCollection()))
            .thenReturn(true);

        orchestrator.onAmbientObserved(sensorId, ambient(31.0, 50.0));

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void safeStopSuppressesWellnessCheckWithoutScenarioOrCommand() {
        robot.changeMode(com.ssafy.bomi.robot.domain.RobotMode.SAFE_STOP);

        orchestrator.onAmbientObserved(sensorId, ambient(31.0, 50.0));

        assertThat(robot.getCurrentMode())
            .isEqualTo(com.ssafy.bomi.robot.domain.RobotMode.SAFE_STOP);
        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void recentCompletionWithinCooldownSuppresses() {
        when(scenarioRepository.existsBySeniorIdAndScenarioTypeAndFinalStatusAndUpdatedAtAfter(
            eq(seniorId), eq(ScenarioType.WELLNESS_CHECK), any(), any()))
            .thenReturn(true);

        orchestrator.onAmbientObserved(sensorId, ambient(31.0, 50.0));

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void missingRobotIsDroppedWithoutThrowing() {
        // 예외가 새어 나가면 브로커가 무한 재전송한다. 시드 미투입 등으로 로봇이
        // 없으면 경고 후 폐기해야 한다.
        when(robotRepository.findBySeniorIdForUpdate(seniorId)).thenReturn(Optional.empty());

        orchestrator.onAmbientObserved(sensorId, ambient(31.0, 50.0)); // must not throw

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void unmappedSensorIsDroppedWithoutThrowing() {
        orchestrator.onAmbientObserved("ghost-sensor", ambient(31.0, 50.0));

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }
}
