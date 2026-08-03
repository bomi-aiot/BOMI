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
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

class WellnessCheckOrchestratorTest {

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final RobotCommandPublisher commandPublisher = mock(RobotCommandPublisher.class);
    private final ObservationProperties observationProperties = new ObservationProperties();
    private final WellnessProperties wellnessProperties = new WellnessProperties();
    private final ObjectMapper objectMapper = new ObjectMapper();

    private WellnessCheckOrchestrator orchestrator;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID robotUuid = UUID.randomUUID();
    private final String sensorId = "ambient-sensor-01";

    @BeforeEach
    void setUp() {
        observationProperties.setAmbientSensorToSenior(Map.of(sensorId, seniorId));
        orchestrator = new WellnessCheckOrchestrator(
            scenarioRepository, robotRepository, commandPublisher,
            new ScenarioStartGuard(scenarioRepository), observationProperties, wellnessProperties);

        when(scenarioRepository.save(any(Scenario.class))).thenAnswer(invocation -> {
            Scenario s = invocation.getArgument(0);
            if (s.getId() == null) {
                ReflectionTestUtils.setField(s, "id", UUID.randomUUID());
            }
            return s;
        });
        Robot robot = Robot.create(seniorId, "robot-01");
        ReflectionTestUtils.setField(robot, "id", robotUuid);
        when(robotRepository.findBySeniorId(seniorId)).thenReturn(Optional.of(robot));
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
    void highTemperatureStartsScenarioWithNavigateAndSpeak() {
        orchestrator.onAmbientObserved(sensorId, ambient(31.0, 50.0));

        ArgumentCaptor<Scenario> scenarioCaptor = ArgumentCaptor.forClass(Scenario.class);
        verify(scenarioRepository).save(scenarioCaptor.capture());
        assertThat(scenarioCaptor.getValue().getScenarioType()).isEqualTo(ScenarioType.WELLNESS_CHECK);

        ArgumentCaptor<RobotCommand> commandCaptor = ArgumentCaptor.forClass(RobotCommand.class);
        verify(commandPublisher, org.mockito.Mockito.times(2)).publish(commandCaptor.capture());
        RobotCommand navigate = commandCaptor.getAllValues().get(0);
        assertThat(navigate.type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(navigate.payload()).containsEntry("target", "LIVING_ROOM");
        assertThat(commandCaptor.getAllValues().get(1).type()).isEqualTo(RobotCommandType.SPEAK);
    }

    @Test
    void highHumidityAloneAlsoTriggers() {
        orchestrator.onAmbientObserved(sensorId, ambient(24.0, 85.0));

        verify(scenarioRepository).save(any(Scenario.class));
    }

    @Test
    void normalReadingDoesNothing() {
        orchestrator.onAmbientObserved(sensorId, ambient(24.0, 50.0));

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
        when(robotRepository.findBySeniorId(seniorId)).thenReturn(Optional.empty());

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
