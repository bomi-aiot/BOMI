package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

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
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

class HomecomingOrchestratorTest {

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final RobotCommandPublisher commandPublisher = mock(RobotCommandPublisher.class);
    private final ConversationGateway conversationGateway = mock(ConversationGateway.class);
    private final HomecomingProperties properties = new HomecomingProperties();

    private HomecomingOrchestrator orchestrator;

    private final UUID seniorId = UUID.randomUUID();
    private final UUID robotUuid = UUID.randomUUID();
    private final String sensorId = "door-sensor-01";
    private final String deviceId = "robot-01";

    @BeforeEach
    void setUp() {
        properties.setSensorToSenior(Map.of(sensorId, seniorId));
        // 가드는 목이 아닌 실물을 쓴다. 판정 재료(exists 쿼리)만 목 리포지토리가 주고,
        // 기본값(false)이면 "막을 이유 없음"이라 기존 테스트는 그대로 통과한다.
        orchestrator = new HomecomingOrchestrator(
            scenarioRepository, robotRepository, commandPublisher, conversationGateway, properties,
            new ScenarioStartGuard(scenarioRepository));
        // Simulate JPA assigning an id on save.
        when(scenarioRepository.save(any(Scenario.class))).thenAnswer(invocation -> {
            Scenario s = invocation.getArgument(0);
            if (s.getId() == null) {
                ReflectionTestUtils.setField(s, "id", UUID.randomUUID());
            }
            return s;
        });
    }

    private Robot robot() {
        Robot robot = Robot.create(seniorId, deviceId);
        ReflectionTestUtils.setField(robot, "id", robotUuid);
        return robot;
    }

    private Scenario scenarioAt(ScenarioStatus status) {
        Scenario s = Scenario.create(seniorId, robotUuid, ScenarioType.HOMECOMING);
        switch (status) {
            case MOVING_TO_ENTRANCE -> s.beginMovingToEntrance();
            case CONVERSING -> {
                s.beginMovingToEntrance();
                s.checkInteraction();
                s.beginConversation();
            }
            case RETURNING_TO_DEFAULT -> {
                s.beginMovingToEntrance();
                s.checkInteraction();
                s.beginConversation();
                s.decideReturn();
                s.returnToDefault();
            }
            default -> { /* RECEIVED: leave as created */ }
        }
        ReflectionTestUtils.setField(s, "id", UUID.randomUUID());
        return s;
    }

    @Test
    void missingRobotIsDroppedWithoutThrowing() {
        // 예외가 새어 나가면 브로커가 무한 재전송한다. 로봇 미배정은 경고 후 폐기.
        when(robotRepository.findBySeniorId(seniorId)).thenReturn(java.util.Optional.empty());

        orchestrator.startHomecoming(sensorId); // must not throw

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void activeScenarioSuppressesNewHomecoming() {
        // 로봇은 한 대뿐이다. 진행 중 시나리오가 있으면 새 귀가 인사를 시작하지 않는다.
        when(scenarioRepository.existsBySeniorIdAndFinalStatusIn(eq(seniorId), anyCollection()))
            .thenReturn(true);

        orchestrator.startHomecoming(sensorId);

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void startHomecomingFromUnmappedSensorIsDroppedWithoutThrowing() {
        // 예외가 새어 나가면 인바운드 엔드포인트가 ack 를 생략해 브로커가
        // 같은 메시지를 무한 재전송한다. 미등록 센서는 조용히 폐기해야 한다.
        orchestrator.startHomecoming("unmapped-sensor"); // must not throw

        verifyNoInteractions(scenarioRepository);
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void startHomecomingCreatesScenarioAndNavigatesToEntrance() {
        when(robotRepository.findBySeniorId(seniorId)).thenReturn(Optional.of(robot()));

        orchestrator.startHomecoming(sensorId);

        ArgumentCaptor<Scenario> scenarioCaptor = ArgumentCaptor.forClass(Scenario.class);
        verify(scenarioRepository).save(scenarioCaptor.capture());
        Scenario saved = scenarioCaptor.getValue();
        assertThat(saved.getScenarioType()).isEqualTo(ScenarioType.HOMECOMING);
        assertThat(saved.getFinalStatus()).isEqualTo(ScenarioStatus.MOVING_TO_ENTRANCE);
        assertThat(saved.getExternalEventId()).isEqualTo(sensorId);

        // 이동과 발화가 함께 나간다 (S15P11E102-226).
        //
        // 예전에는 인사가 '도착한 뒤'에 나갔다. 그러면 느리거나 실패한 이동이 인사를
        // 통째로 삼키는데, 인사의 마감 시간은 약 45초로 의자를 돌아가는 경로 계산보다
        // 짧다. 목소리는 방을 건너 들리므로 바퀴를 기다릴 이유가 없다 (CLAUDE.md §11).
        ArgumentCaptor<RobotCommand> commandCaptor = ArgumentCaptor.forClass(RobotCommand.class);
        verify(commandPublisher, times(2)).publish(commandCaptor.capture());

        RobotCommand navigate = commandCaptor.getAllValues().stream()
            .filter(c -> c.type() == RobotCommandType.NAVIGATE).findFirst().orElseThrow();
        assertThat(navigate.robotId()).isEqualTo(deviceId);
        assertThat(navigate.payload()).containsEntry("target", "ENTRANCE");
        assertThat(navigate.scenarioId()).isNotNull();

        assertThat(commandCaptor.getAllValues())
            .anyMatch(c -> c.type() == RobotCommandType.SPEAK);
    }

    @Test
    void arrivalAtEntranceHandsOffToConversationWithoutSpeakingAgain() {
        /*
         * ★ 인사는 startHomecoming 에서 이미 나갔다 (S15P11E102-226).
         *
         * 도착 시점에 또 말하면 어르신은 같은 인사를 두 번 듣고, 두 번째는 로봇이
         * 도착한 뒤라 한참 늦다. 도착이 하는 일은 대화로 넘기는 것뿐이다.
         */
        Scenario scenario = scenarioAt(ScenarioStatus.MOVING_TO_ENTRANCE);
        UUID scenarioId = scenario.getId();
        when(scenarioRepository.findById(scenarioId)).thenReturn(Optional.of(scenario));
        when(robotRepository.findById(robotUuid)).thenReturn(Optional.of(robot()));

        orchestrator.onRobotArrived(scenarioId);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.CONVERSING);
        verify(commandPublisher, never()).publish(any());
        verify(conversationGateway).startConversation(scenarioId, seniorId);
    }

    @Test
    void conversationEndedNavigatesBackToDefault() {
        Scenario scenario = scenarioAt(ScenarioStatus.CONVERSING);
        UUID scenarioId = scenario.getId();
        when(scenarioRepository.findById(scenarioId)).thenReturn(Optional.of(scenario));
        when(robotRepository.findById(robotUuid)).thenReturn(Optional.of(robot()));

        orchestrator.onConversationEnded(scenarioId);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        ArgumentCaptor<RobotCommand> commandCaptor = ArgumentCaptor.forClass(RobotCommand.class);
        verify(commandPublisher).publish(commandCaptor.capture());
        assertThat(commandCaptor.getValue().type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(commandCaptor.getValue().payload()).containsEntry("target", "DEFAULT");
    }

    @Test
    void arrivalAfterReturnCompletesScenario() {
        Scenario scenario = scenarioAt(ScenarioStatus.RETURNING_TO_DEFAULT);
        UUID scenarioId = scenario.getId();
        Robot robot = robot();
        robot.changeMode(RobotMode.SCENARIO_ACTIVE);
        when(scenarioRepository.findById(scenarioId)).thenReturn(Optional.of(scenario));
        when(robotRepository.findById(robotUuid)).thenReturn(Optional.of(robot));

        orchestrator.onRobotArrived(scenarioId);

        assertThat(scenario.getFinalStatus()).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.IDLE); // mode synced on completion
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void arrivalForUnknownScenarioIsIgnored() {
        UUID unknown = UUID.randomUUID();
        when(scenarioRepository.findById(unknown)).thenReturn(Optional.empty());

        orchestrator.onRobotArrived(unknown); // must not throw

        verifyNoInteractions(commandPublisher);
    }
}
