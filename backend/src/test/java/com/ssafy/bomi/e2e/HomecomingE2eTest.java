package com.ssafy.bomi.e2e;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.mqtt.inbound.InMemoryProcessedEventStore;
import com.ssafy.bomi.mqtt.inbound.MqttInboundDispatcher;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.observation.application.RobotObservationService;
import com.ssafy.bomi.observation.config.ObservationProperties;
import com.ssafy.bomi.observation.inbound.AmbientObservedHandler;
import com.ssafy.bomi.observation.inbound.NavigationStatusHandler;
import com.ssafy.bomi.observation.inbound.RestStateChangedHandler;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.application.ConversationGateway;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.inbound.ConversationEndedHandler;
import com.ssafy.bomi.scenario.inbound.DoorOpenedHandler;
import com.ssafy.bomi.scenario.inbound.NavigationResultHandler;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

/**
 * End-to-end "logic" test of the homecoming flow over a real (H2) database.
 *
 * <p>Method A: no MQTT broker. Real Spring Data repositories come from
 * {@code @DataJpaTest}; the processing chain (dispatcher → idempotency → handlers
 * → orchestrator → scenario state machine → observation) is wired by hand, and
 * outbound commands are captured by a recording {@link RobotCommandPublisher}.
 * Inbound is driven by feeding {@link MqttInboundMessage}s to the dispatcher,
 * exactly as the transport layer would after parsing. The Paho transport itself
 * is covered by the MQTT skeleton's own unit tests.</p>
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class HomecomingE2eTest {

    @Autowired ScenarioRepository scenarioRepository;
    @Autowired RobotRepository robotRepository;
    @Autowired CareRecordRepository careRecordRepository;
    @Autowired TestEntityManager em;

    private final ObjectMapper objectMapper = new ObjectMapper();

    private static final String SENSOR_ID = "door-sensor-01";
    private static final String DEVICE_ID = "robot-01";

    private RecordingPublisher publisher;
    private RecordingGateway gateway;
    private HomecomingOrchestrator orchestrator;
    private MqttInboundDispatcher dispatcher;

    private UUID seniorId;
    private UUID robotId;

    @BeforeEach
    void setUp() {
        // Seed a robot assigned to a senior, addressable by its device id.
        seniorId = UUID.randomUUID();
        Robot robot = robotRepository.saveAndFlush(Robot.create(seniorId, DEVICE_ID));
        robotId = robot.getId();

        HomecomingProperties homecomingProperties = new HomecomingProperties();
        homecomingProperties.setSensorToSenior(Map.of(SENSOR_ID, seniorId));
        ObservationProperties observationProperties = new ObservationProperties();

        publisher = new RecordingPublisher();
        gateway = new RecordingGateway();

        orchestrator = new HomecomingOrchestrator(
            scenarioRepository, robotRepository, publisher, gateway, homecomingProperties);
        RobotObservationService observationService = new RobotObservationService(
            robotRepository, careRecordRepository, observationProperties);

        List<MqttMessageHandler> handlers = List.of(
            new DoorOpenedHandler(orchestrator),
            new NavigationResultHandler(orchestrator),
            new ConversationEndedHandler(orchestrator),
            new RestStateChangedHandler(observationService),
            new AmbientObservedHandler(observationService),
            new NavigationStatusHandler());
        dispatcher = new MqttInboundDispatcher(handlers, new InMemoryProcessedEventStore());
    }

    @Test
    void doorOpenedRunsThroughToCompleted() {
        // 1) Door opens → scenario created, NAVIGATE(entrance) + SPEAK, robot SCENARIO_ACTIVE.
        //
        //    발화가 이동과 함께 나간다 (S15P11E102-226). 예전에는 도착 뒤에 말했는데,
        //    그러면 느리거나 실패한 이동이 인사를 삼킨다 (CLAUDE.md §11).
        dispatcher.dispatch(doorOpened("door-1"));
        sync();

        assertThat(publisher.commands).hasSize(2);
        assertThat(publisher.commands.get(1).type()).isEqualTo(RobotCommandType.SPEAK);
        RobotCommand navToEntrance = publisher.commands.get(0);
        assertThat(navToEntrance.type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(navToEntrance.robotId()).isEqualTo(DEVICE_ID);
        assertThat(navToEntrance.payload()).containsEntry("target", "ENTRANCE");

        UUID scenarioId = navToEntrance.scenarioId();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.MOVING_TO_ENTRANCE);
        assertThat(mode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);

        // 2) Robot arrives at entrance → conversation hand-off only. 인사는 이미 나갔다.
        dispatcher.dispatch(navigationResult("nav-1", scenarioId));
        sync();

        assertThat(publisher.commands).hasSize(2);  // 도착이 명령을 더하지 않는다
        assertThat(gateway.startedScenarioIds).containsExactly(scenarioId);
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.CONVERSING);

        // 3) Voice side publishes CONVERSATION_ENDED → NAVIGATE(default).
        dispatcher.dispatch(conversationEnded("conv-1", scenarioId));
        sync();

        RobotCommand navHome = publisher.commands.get(2);
        assertThat(navHome.type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(navHome.payload()).containsEntry("target", "DEFAULT");
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);

        // 4) Robot arrives home → COMPLETED, robot back to IDLE.
        dispatcher.dispatch(navigationResult("nav-2", scenarioId));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(mode()).isEqualTo(RobotMode.IDLE);
        assertThat(publisher.commands).hasSize(3);
    }

    @Test
    void duplicateDoorOpenedCreatesOnlyOneScenario() {
        dispatcher.dispatch(doorOpened("door-1"));
        dispatcher.dispatch(doorOpened("door-1")); // same eventId → must be skipped
        sync();

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(publisher.commands).hasSize(2);  // 두 번째 문 열림은 무시된다
    }

    @Test
    void conversationEndedIgnoredWhenNotConversing() {
        // Door opened → scenario is MOVING_TO_ENTRANCE, not CONVERSING yet.
        dispatcher.dispatch(doorOpened("door-1"));
        sync();
        UUID scenarioId = publisher.commands.get(0).scenarioId();

        // A CONVERSATION_ENDED arriving now must be ignored by the status guard.
        dispatcher.dispatch(conversationEnded("conv-early", scenarioId));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.MOVING_TO_ENTRANCE);
        assertThat(publisher.commands).hasSize(2); // 여전히 NAVIGATE(ENTRANCE) + SPEAK 뿐
    }

    @Test
    void lateConversationEndedIgnoredAfterReturnStarted() {
        dispatcher.dispatch(doorOpened("door-1"));
        sync();
        UUID scenarioId = publisher.commands.get(0).scenarioId();
        dispatcher.dispatch(navigationResult("nav-1", scenarioId));
        sync();
        dispatcher.dispatch(conversationEnded("conv-1", scenarioId)); // → NAVIGATE(default)
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        assertThat(publisher.commands).hasSize(3);

        // A late CONVERSATION_ENDED with a NEW eventId passes idempotency but the
        // status guard ignores it (no longer CONVERSING): no extra command.
        dispatcher.dispatch(conversationEnded("conv-2", scenarioId));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        assertThat(publisher.commands).hasSize(3);
    }

    @Test
    void navigationFailureStopsScenarioAndSafeStops() {
        dispatcher.dispatch(doorOpened("door-1"));
        sync();
        UUID scenarioId = publisher.commands.get(0).scenarioId();

        // Robot fails to reach the entrance → scenario FAILED, robot SAFE_STOP, no SPEAK.
        dispatcher.dispatch(navigationResult("nav-1", scenarioId, "FAILED"));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.FAILED);
        assertThat(mode()).isEqualTo(RobotMode.SAFE_STOP);
        assertThat(publisher.commands).hasSize(2); // NAVIGATE(ENTRANCE) + SPEAK, 그 뒤로 없음
    }

    @Test
    void navigationResultWithoutStatusIsIgnoredNotTreatedAsArrival() {
        dispatcher.dispatch(doorOpened("door-1"));
        sync();
        UUID scenarioId = publisher.commands.get(0).scenarioId();

        // A result missing 'status' must NOT be treated as arrival: state unchanged.
        ObjectNode body = objectMapper.createObjectNode();
        body.putObject("payload").put("scenarioId", scenarioId.toString());
        dispatcher.dispatch(message(
            MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", DEVICE_ID, "nav-nostatus", body));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.MOVING_TO_ENTRANCE);
        assertThat(publisher.commands).hasSize(2);
    }

    @Test
    void lateNavigationFailureIgnoredAfterTerminal() {
        dispatcher.dispatch(doorOpened("door-1"));
        sync();
        UUID scenarioId = publisher.commands.get(0).scenarioId();
        dispatcher.dispatch(navigationResult("nav-1", scenarioId, "FAILED"));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.FAILED);

        // A late failure with a new eventId must be ignored (already terminal).
        dispatcher.dispatch(navigationResult("nav-2", scenarioId, "FAILED"));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.FAILED);
        assertThat(publisher.commands).hasSize(2);
    }

    @Test
    void restStateChangeRecordsObservationAndEntersRestGuard() {
        dispatcher.dispatch(restState("rest-1", "RESTING"));
        sync();

        assertThat(mode()).isEqualTo(RobotMode.REST_GUARD);
        assertThat(careRecordRepository.findAll())
            .anySatisfy(record -> assertThat(record.getRecordType()).isEqualTo("REST_OBSERVATION"));
    }

    // --- helpers -------------------------------------------------------------

    /** Flush pending writes and detach so each subsequent step reloads from the DB. */
    private void sync() {
        em.flush();
        em.clear();
    }

    private ScenarioStatus status(UUID scenarioId) {
        Scenario scenario = scenarioRepository.findById(scenarioId).orElseThrow();
        return scenario.getFinalStatus();
    }

    private RobotMode mode() {
        return robotRepository.findById(robotId).orElseThrow().getCurrentMode();
    }

    private MqttInboundMessage message(
        MqttInboundCategory category, String type, String sourceId, String eventId, JsonNode body) {
        return new MqttInboundMessage(
            category, "bomi/v1/topic", sourceId, eventId, type, OffsetDateTime.now(), 1, false, body);
    }

    private MqttInboundMessage doorOpened(String eventId) {
        return message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", SENSOR_ID, eventId, null);
    }

    private MqttInboundMessage navigationResult(String eventId, UUID scenarioId) {
        return navigationResult(eventId, scenarioId, "ARRIVED");
    }

    private MqttInboundMessage navigationResult(String eventId, UUID scenarioId, String status) {
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("scenarioId", scenarioId.toString());
        payload.put("status", status);
        return message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", DEVICE_ID, eventId, body);
    }

    private MqttInboundMessage conversationEnded(String eventId, UUID scenarioId) {
        ObjectNode body = objectMapper.createObjectNode();
        body.putObject("payload").put("scenarioId", scenarioId.toString());
        return message(MqttInboundCategory.ROBOT_EVENT, "CONVERSATION_ENDED", DEVICE_ID, eventId, body);
    }

    private MqttInboundMessage restState(String eventId, String state) {
        ObjectNode body = objectMapper.createObjectNode();
        body.putObject("payload").put("restState", state);
        return message(MqttInboundCategory.ROBOT_STATUS, "REST_STATE_CHANGED", DEVICE_ID, eventId, body);
    }

    // --- test doubles --------------------------------------------------------

    private static final class RecordingPublisher implements RobotCommandPublisher {
        private final List<RobotCommand> commands = new ArrayList<>();

        @Override
        public void publish(RobotCommand command) {
            commands.add(command);
        }
    }

    private static final class RecordingGateway implements ConversationGateway {
        private final List<UUID> startedScenarioIds = new ArrayList<>();

        @Override
        public void startConversation(UUID scenarioId, UUID seniorId) {
            startedScenarioIds.add(scenarioId);
        }
    }
}
