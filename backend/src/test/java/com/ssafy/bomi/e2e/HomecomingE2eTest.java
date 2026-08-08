package com.ssafy.bomi.e2e;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.conversation.domain.ConversationOutcome;
import com.ssafy.bomi.conversation.domain.ConversationStatus;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.mqtt.inbound.InMemoryProcessedEventStore;
import com.ssafy.bomi.mqtt.inbound.MqttInboundDispatcher;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.outbound.AiConversationCommand;
import com.ssafy.bomi.mqtt.outbound.AiConversationCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.observation.application.RobotObservationService;
import com.ssafy.bomi.observation.config.ObservationProperties;
import com.ssafy.bomi.observation.config.WellnessProperties;
import com.ssafy.bomi.observation.inbound.AmbientObservedHandler;
import com.ssafy.bomi.observation.inbound.NavigationStatusHandler;
import com.ssafy.bomi.observation.inbound.RestStateChangedHandler;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import com.ssafy.bomi.scenario.application.MedicationReminderScheduler;
import com.ssafy.bomi.scenario.application.MqttConversationGateway;
import com.ssafy.bomi.scenario.application.FollowResultRouter;
import com.ssafy.bomi.scenario.application.NavigationResultRouter;
import com.ssafy.bomi.scenario.application.ScenarioRobotStartPolicy;
import com.ssafy.bomi.scenario.application.ScenarioStartGuard;
import com.ssafy.bomi.scenario.application.WakeWordCallOrchestrator;
import com.ssafy.bomi.scenario.application.WalkOrchestrator;
import com.ssafy.bomi.scenario.application.WellnessCheckOrchestrator;
import com.ssafy.bomi.occupancy.config.EntranceProperties;
import com.ssafy.bomi.scenario.config.AiConversationProperties;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import com.ssafy.bomi.scenario.config.MedicationReminderProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.inbound.ConversationEndedHandler;
import com.ssafy.bomi.scenario.inbound.ConversationStartedHandler;
import com.ssafy.bomi.scenario.inbound.DoorOpenedHandler;
import com.ssafy.bomi.scenario.inbound.FollowResultHandler;
import com.ssafy.bomi.scenario.inbound.NavigationResultHandler;
import com.ssafy.bomi.scenario.inbound.WakeWordDetectedHandler;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.scenario.repository.WakeWordTriggerReceiptRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
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

/** End-to-end homecoming logic over a real H2 persistence context, without a broker. */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class HomecomingE2eTest {

    private static final String SENSOR_ID = "door-sensor-01";
    private static final String AMBIENT_SENSOR_ID = "ambient-sensor-01";
    private static final String DEVICE_ID = "robot-01";

    @Autowired ScenarioRepository scenarioRepository;
    @Autowired WakeWordTriggerReceiptRepository wakeWordTriggerReceiptRepository;
    @Autowired ConversationRepository conversationRepository;
    @Autowired RobotRepository robotRepository;
    @Autowired CareRecordRepository careRecordRepository;
    @Autowired AppUserRepository appUserRepository;
    @Autowired TestEntityManager em;

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final Clock clock = Clock.fixed(
        Instant.parse("2026-08-05T01:00:00Z"), ZoneOffset.UTC);

    private RecordingRobotPublisher robotPublisher;
    private RecordingAiPublisher aiPublisher;
    private List<MqttMessageHandler> handlers;
    private MqttInboundDispatcher dispatcher;
    private MedicationReminderScheduler medicationScheduler;
    private UUID seniorId;
    private UUID robotId;

    @BeforeEach
    void setUp() {
        seniorId = appUserRepository.saveAndFlush(AppUser.create("SENIOR", "호출 테스트 시니어"))
            .getId();
        Robot robot = robotRepository.saveAndFlush(Robot.create(seniorId, DEVICE_ID));
        robotId = robot.getId();

        HomecomingProperties homecomingProperties = new HomecomingProperties();
        homecomingProperties.setSensorToSenior(Map.of(SENSOR_ID, seniorId));
        ObservationProperties observationProperties = new ObservationProperties();
        observationProperties.setAmbientSensorToSenior(Map.of(AMBIENT_SENSOR_ID, seniorId));

        robotPublisher = new RecordingRobotPublisher();
        aiPublisher = new RecordingAiPublisher();
        ScenarioStartGuard startGuard =
            new ScenarioStartGuard(scenarioRepository, appUserRepository);
        ScenarioRobotStartPolicy startPolicy = new ScenarioRobotStartPolicy(
            startGuard, robotRepository, scenarioRepository);
        MqttConversationGateway gateway = new MqttConversationGateway(
            scenarioRepository,
            conversationRepository,
            robotRepository,
            aiPublisher,
            new AiConversationProperties(),
            clock);
        HomecomingOrchestrator orchestrator = new HomecomingOrchestrator(
            scenarioRepository,
            conversationRepository,
            robotRepository,
            robotPublisher,
            gateway,
            homecomingProperties,
            startPolicy,
            clock);
        WakeWordCallOrchestrator wakeWordCallOrchestrator =
            new WakeWordCallOrchestrator(
                scenarioRepository,
                wakeWordTriggerReceiptRepository,
                robotRepository,
                robotPublisher,
                startPolicy,
                clock);
        NavigationResultRouter navigationResultRouter = new NavigationResultRouter(
            scenarioRepository, orchestrator, wakeWordCallOrchestrator);
        // 보미야 호출은 이제 FOLLOW_START 로 로봇의 회전 탐색을 켠다. 산책은 이
        // E2E 의 범위 밖이라 대역으로 둔다 — 여기 도착하는 결과는 전부
        // WAKE_WORD_CALL 시나리오다.
        FollowResultRouter followResultRouter = new FollowResultRouter(
            scenarioRepository, wakeWordCallOrchestrator, orchestrator,
            mock(WalkOrchestrator.class));

        RobotObservationService observationService = new RobotObservationService(
            robotRepository, careRecordRepository, observationProperties);
        WellnessCheckOrchestrator wellnessOrchestrator = new WellnessCheckOrchestrator(
            scenarioRepository, robotRepository, robotPublisher, startPolicy,
            observationProperties, new WellnessProperties());
        medicationScheduler = new MedicationReminderScheduler(
            careRecordRepository,
            scenarioRepository,
            robotRepository,
            robotPublisher,
            startPolicy,
            new MedicationReminderProperties(),
            clock);

        handlers = List.of(
            // S15P11E102-365(PIR 방향 판정)가 생성자를 넷으로 늘렸는데 이 E2E 만
            // 갱신되지 않아 테스트 트리 전체가 컴파일되지 않았다.
            //
            // EntranceProperties 의 directionResolutionEnabled 기본값이 false 이고,
            // 꺼져 있으면 handle() 이 orchestrator.startHomecoming 만 부르고 즉시
            // 반환한다 — doorEventService 와 homecomingProperties 에는 닿지 않는다.
            // 그래서 이 테스트가 검증하는 옛 경로(문 열림 하나로 귀가 시작)는 그대로다.
            //
            // ★ 이 테스트에서 방향 판정을 켜려면 doorEventService 를 진짜로 만들어야
            //   한다. null 이 남아 있는 채로 켜면 NPE 로 죽는다.
            new DoorOpenedHandler(orchestrator, null, new HomecomingProperties(),
                new EntranceProperties()),
            new WakeWordDetectedHandler(wakeWordCallOrchestrator),
            new NavigationResultHandler(navigationResultRouter),
            new FollowResultHandler(followResultRouter),
            new ConversationStartedHandler(orchestrator),
            new ConversationEndedHandler(orchestrator),
            new RestStateChangedHandler(observationService),
            new AmbientObservedHandler(observationService, wellnessOrchestrator),
            new NavigationStatusHandler());
        dispatcher = new MqttInboundDispatcher(handlers, new InMemoryProcessedEventStore());
    }

    @Test
    void wakeWordCallStartsTheSearchAndCompletesWithoutConversationOrReturn() {
        assertThat(mode()).isEqualTo(RobotMode.IDLE);

        dispatcher.dispatch(wakeWordDetected("wake-1"));
        sync();

        assertThat(robotPublisher.commands).hasSize(1);
        RobotCommand followStart = robotPublisher.commands.get(0);
        assertThat(followStart.type()).isEqualTo(RobotCommandType.FOLLOW_START);
        assertThat(followStart.payload()).isEmpty();
        UUID scenarioId = followStart.scenarioId();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.NAVIGATING);
        assertThat(mode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(conversationRepository.findAll()).isEmpty();
        assertThat(aiPublisher.commands).isEmpty();

        // STARTED 는 접수 확인이다. 탐색 결과는 로봇 안에서 끝나고 보고되지 않는다.
        dispatcher.dispatch(followResult(
            "wake-follow-1", scenarioId, followStart.commandId(), "SUCCEEDED"));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(mode()).isEqualTo(RobotMode.IDLE);
        assertThat(robotPublisher.commands).hasSize(1);
        assertThat(robotPublisher.commands)
            .noneMatch(command -> "DEFAULT".equals(command.payload().get("target")));
        assertThat(conversationRepository.findAll()).isEmpty();
        assertThat(aiPublisher.commands).isEmpty();
    }

    @Test
    void duplicateWakeWordEventIsANoOpAfterTheFirstDelivery() {
        dispatcher.dispatch(wakeWordDetected("wake-duplicate"));
        sync();

        // Simulate a restarted process whose in-memory event cache is empty.
        dispatcher = new MqttInboundDispatcher(handlers, new InMemoryProcessedEventStore());
        dispatcher.dispatch(wakeWordDetected("wake-duplicate"));
        sync();

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(robotPublisher.commands).hasSize(1);
        assertThat(robotPublisher.commands.get(0).type())
            .isEqualTo(RobotCommandType.FOLLOW_START);
    }

    @Test
    void activeHomecomingSuppressesWakeWordMovementCommand() {
        dispatcher.dispatch(doorOpened("door-active-before-wake"));
        sync();

        assertThat(robotPublisher.commands).hasSize(1);
        assertThat(robotPublisher.commands.get(0).payload())
            .containsEntry("target", "ENTRANCE");

        dispatcher.dispatch(wakeWordDetected("wake-while-active"));
        sync();

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(robotPublisher.commands).hasSize(1);
        assertThat(robotPublisher.commands)
            .noneMatch(command -> command.type() == RobotCommandType.FOLLOW_START);
    }

    @Test
    void doorOpenedRunsThroughRealAiCommandAndConversationLifecycle() {
        dispatcher.dispatch(doorOpened("door-1"));
        sync();

        assertThat(robotPublisher.commands).hasSize(1);
        RobotCommand entrance = robotPublisher.commands.get(0);
        assertThat(entrance.type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(entrance.payload()).containsEntry("target", "ENTRANCE");
        UUID scenarioId = entrance.scenarioId();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.MOVING_TO_ENTRANCE);
        assertThat(mode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);

        dispatcher.dispatch(navigationResult(
            "nav-1", scenarioId, entrance.commandId(), "SUCCEEDED"));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.CHECKING_INTERACTION);
        assertThat(aiPublisher.commands).hasSize(1);
        AiConversationCommand aiCommand = aiPublisher.commands.get(0);
        assertThat(aiCommand.scenarioId()).isEqualTo(scenarioId);
        assertThat(aiCommand.payload().text()).isNotBlank();
        Conversation conversation = conversationRepository.findByScenarioId(scenarioId).orElseThrow();
        assertThat(aiCommand.conversationId()).isEqualTo(conversation.getId());
        assertThat(conversation.getAiStartedAt()).isNull();

        dispatcher.dispatch(conversationStarted(
            "conv-start-1",
            scenarioId,
            conversation.getId(),
            conversation.getStartCommandId(),
            ConversationIntent.HOMECOMING_GREETING));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.CONVERSING);
        assertThat(conversationRepository.findById(conversation.getId()).orElseThrow()
            .getAiStartedAt()).isNotNull();

        dispatcher.dispatch(conversationEnded(
            "conv-end-1", scenarioId, conversation.getId(), "COMPLETED", null));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.STARTING_FOLLOW);
        assertThat(robotPublisher.commands).hasSize(2);
        assertThat(robotPublisher.commands.get(1).type())
            .isEqualTo(RobotCommandType.FOLLOW_START);
        assertThat(robotPublisher.commands.get(1).payload()).isEmpty();

        // A distinct duplicate event must also be harmless after an app restart lost eventId memory.
        dispatcher.dispatch(conversationEnded(
            "conv-end-2", scenarioId, conversation.getId(), "COMPLETED", null));
        sync();
        assertThat(robotPublisher.commands).hasSize(2);

        RobotCommand followStart = robotPublisher.commands.get(1);
        dispatcher.dispatch(followResult(
            "follow-1", scenarioId, followStart.commandId(), "SUCCEEDED"));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.FOLLOWING);
        assertThat(mode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        Conversation ended = conversationRepository.findById(conversation.getId()).orElseThrow();
        assertThat(ended.getStatus()).isEqualTo(ConversationStatus.COMPLETED);
        assertThat(ended.getEndOutcome()).isEqualTo(ConversationOutcome.COMPLETED);
    }

    @Test
    void legacyNavigationResultStillStartsAiDuringRobotMigration() {
        dispatcher.dispatch(doorOpened("door-legacy"));
        sync();
        UUID scenarioId = robotPublisher.commands.get(0).scenarioId();

        dispatcher.dispatch(legacyNavigationResult("legacy-nav", scenarioId, "ARRIVED"));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.CHECKING_INTERACTION);
        assertThat(aiPublisher.commands).hasSize(1);
    }

    @Test
    void duplicateDoorEventCreatesOnlyOneScenarioAndCommand() {
        dispatcher.dispatch(doorOpened("door-duplicate"));
        dispatcher.dispatch(doorOpened("door-duplicate"));
        sync();

        assertThat(scenarioRepository.findAll()).hasSize(1);
        assertThat(robotPublisher.commands).hasSize(1);
    }

    @Test
    void navigationFailureSafeStopsBeforeConversationStarts() {
        dispatcher.dispatch(doorOpened("door-failure"));
        sync();
        RobotCommand entrance = robotPublisher.commands.get(0);
        UUID scenarioId = entrance.scenarioId();

        dispatcher.dispatch(navigationResult(
            "nav-failure", scenarioId, entrance.commandId(), "FAILED"));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.FAILED);
        assertThat(mode()).isEqualTo(RobotMode.SAFE_STOP);
        assertThat(aiPublisher.commands).isEmpty();
    }

    @Test
    void highAmbientTemperatureRunsThroughAiConversationAndReturnsHome() {
        dispatcher.dispatch(ambientObserved("amb-1", 31.5));
        sync();

        assertThat(robotPublisher.commands).hasSize(1);
        RobotCommand navigate = robotPublisher.commands.get(0);
        assertThat(navigate.payload()).containsEntry("target", "LIVING_ROOM");
        assertThat(mode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);

        dispatcher.dispatch(navigationResult(
            "amb-nav-1", navigate.scenarioId(), navigate.commandId(), "SUCCEEDED"));
        sync();

        UUID scenarioId = navigate.scenarioId();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.CHECKING_INTERACTION);
        assertThat(aiPublisher.commands).hasSize(1);
        AiConversationCommand aiCommand = aiPublisher.commands.get(0);
        assertThat(aiCommand.payload().intent()).isEqualTo(ConversationIntent.WELLNESS_CHECK);
        assertThat(aiCommand.payload().triggerContext())
            .containsEntry("location", "LIVING_ROOM");
        assertThat(((Number) aiCommand.payload().triggerContext().get("temperatureC"))
            .doubleValue()).isEqualTo(31.5);
        Conversation conversation = conversationRepository.findByScenarioId(scenarioId)
            .orElseThrow();

        dispatcher.dispatch(conversationStarted(
            "amb-conv-start-1",
            scenarioId,
            conversation.getId(),
            conversation.getStartCommandId(),
            ConversationIntent.WELLNESS_CHECK));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.CONVERSING);

        dispatcher.dispatch(conversationEnded(
            "amb-conv-end-1", scenarioId, conversation.getId(), "COMPLETED", null));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        assertThat(robotPublisher.commands).hasSize(2);
        RobotCommand returnToDefault = robotPublisher.commands.get(1);
        assertThat(returnToDefault.payload()).containsEntry("target", "DEFAULT");

        dispatcher.dispatch(navigationResult(
            "amb-nav-2",
            scenarioId,
            returnToDefault.commandId(),
            "SUCCEEDED"));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(mode()).isEqualTo(RobotMode.IDLE);
    }

    @Test
    void dueMedicationRunsThroughAiConversationAndReturnsHome() {
        CareRecord medication = careRecordRepository.saveAndFlush(CareRecord.create(
            seniorId,
            "MEDICATION",
            Map.of("medicationName", "혈압약", "reminderEnabled", true)));
        CareRecord schedule = CareRecord.create(
            seniorId,
            "MEDICATION_SCHEDULE",
            Map.of(
                "medicationName", "혈압약",
                "localTimes", List.of("10:00"),
                "timeZone", "Asia/Seoul",
                "reminderLeadMinutes", 0));
        schedule.assignParent(medication.getId());
        careRecordRepository.saveAndFlush(schedule);

        medicationScheduler.tick();
        sync();

        assertThat(robotPublisher.commands).hasSize(1);
        RobotCommand navigate = robotPublisher.commands.get(0);
        assertThat(navigate.payload()).containsEntry("target", "LIVING_ROOM");
        UUID scenarioId = navigate.scenarioId();

        dispatcher.dispatch(navigationResult(
            "med-nav-1", scenarioId, navigate.commandId(), "SUCCEEDED"));
        sync();

        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.CHECKING_INTERACTION);
        assertThat(aiPublisher.commands).hasSize(1);
        AiConversationCommand aiCommand = aiPublisher.commands.get(0);
        assertThat(aiCommand.payload().intent())
            .isEqualTo(ConversationIntent.MEDICATION_REMINDER);
        assertThat(aiCommand.payload().text()).contains("혈압약");
        assertThat(aiCommand.payload().triggerContext())
            .containsEntry("medicationScheduleId", schedule.getId().toString())
            .containsEntry("scheduledAt", "2026-08-05T10:00+09:00");
        Conversation conversation = conversationRepository.findByScenarioId(scenarioId)
            .orElseThrow();

        dispatcher.dispatch(conversationStarted(
            "med-conv-start-1",
            scenarioId,
            conversation.getId(),
            conversation.getStartCommandId(),
            ConversationIntent.MEDICATION_REMINDER));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.CONVERSING);

        dispatcher.dispatch(conversationEnded(
            "med-conv-end-1", scenarioId, conversation.getId(), "COMPLETED", null));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.RETURNING_TO_DEFAULT);
        assertThat(robotPublisher.commands).hasSize(2);
        RobotCommand returnToDefault = robotPublisher.commands.get(1);
        assertThat(returnToDefault.payload()).containsEntry("target", "DEFAULT");

        dispatcher.dispatch(navigationResult(
            "med-nav-2",
            scenarioId,
            returnToDefault.commandId(),
            "SUCCEEDED"));
        sync();
        assertThat(status(scenarioId)).isEqualTo(ScenarioStatus.COMPLETED);
        assertThat(mode()).isEqualTo(RobotMode.IDLE);
    }

    @Test
    void normalAmbientTemperatureOnlyRecordsObservation() {
        dispatcher.dispatch(ambientObserved("amb-normal", 24.0));
        sync();

        assertThat(robotPublisher.commands).isEmpty();
        assertThat(scenarioRepository.findAll()).isEmpty();
        assertThat(careRecordRepository.findAll())
            .anySatisfy(record -> assertThat(record.getRecordType())
                .isEqualTo("ENVIRONMENT_OBSERVATION"));
    }

    @Test
    void restStateChangeStillEntersRestGuard() {
        dispatcher.dispatch(restState("rest-1", "RESTING"));
        sync();

        assertThat(mode()).isEqualTo(RobotMode.REST_GUARD);
    }

    private void sync() {
        em.flush();
        em.clear();
    }

    private ScenarioStatus status(UUID scenarioId) {
        return scenarioRepository.findById(scenarioId).orElseThrow().getFinalStatus();
    }

    private RobotMode mode() {
        return robotRepository.findById(robotId).orElseThrow().getCurrentMode();
    }

    private MqttInboundMessage message(
        MqttInboundCategory category,
        String type,
        String sourceId,
        String eventId,
        UUID scenarioId,
        UUID conversationId,
        String commandId,
        boolean legacy,
        JsonNode body
    ) {
        return new MqttInboundMessage(
            category,
            "bomi/v1/topic",
            sourceId,
            eventId,
            type,
            OffsetDateTime.now(clock),
            1,
            false,
            scenarioId,
            conversationId,
            commandId,
            legacy,
            body);
    }

    private MqttInboundMessage doorOpened(String eventId) {
        return message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", SENSOR_ID, eventId,
            null, null, null, false, null);
    }

    private MqttInboundMessage wakeWordDetected(String eventId) {
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("keyword", "bomi");
        payload.put("confidence", 0.92);
        return message(MqttInboundCategory.ROBOT_EVENT, "WAKE_WORD_DETECTED", DEVICE_ID, eventId,
            null, null, null, false, body);
    }

    private MqttInboundMessage navigationResult(
        String eventId,
        UUID scenarioId,
        String commandId,
        String outcome
    ) {
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        boolean success = "SUCCEEDED".equals(outcome);
        payload.put("outcome", outcome);
        payload.put("resultCode", success ? "ARRIVED" : "NOT_ARRIVED");
        if (success) {
            payload.putNull("reasonCode");
        } else {
            payload.put("reasonCode", "PATH_BLOCKED");
        }
        return message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", DEVICE_ID, eventId,
            scenarioId, null, commandId, false, body);
    }

    private MqttInboundMessage followResult(
        String eventId,
        UUID scenarioId,
        String commandId,
        String outcome
    ) {
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        boolean success = "SUCCEEDED".equals(outcome);
        payload.put("outcome", outcome);
        // FOLLOW 어휘는 STARTED/UNCHANGED 다 — ARRIVED/NOT_ARRIVED 가 아니다.
        payload.put("resultCode", success ? "STARTED" : "UNCHANGED");
        if (success) {
            payload.putNull("reasonCode");
        } else {
            payload.put("reasonCode", "INTERNAL_ERROR");
        }
        return message(MqttInboundCategory.ROBOT_RESULT, "FOLLOW_RESULT", DEVICE_ID, eventId,
            scenarioId, null, commandId, false, body);
    }

    private MqttInboundMessage legacyNavigationResult(
        String eventId,
        UUID scenarioId,
        String status
    ) {
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("scenarioId", scenarioId.toString());
        payload.put("status", status);
        return message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", DEVICE_ID, eventId,
            scenarioId, null, null, true, body);
    }

    private MqttInboundMessage conversationStarted(
        String eventId,
        UUID scenarioId,
        UUID conversationId,
        String commandId,
        ConversationIntent intent
    ) {
        ObjectNode body = objectMapper.createObjectNode();
        body.putObject("payload").put("intent", intent.name());
        return message(MqttInboundCategory.ROBOT_EVENT, "CONVERSATION_STARTED", DEVICE_ID, eventId,
            scenarioId, conversationId, commandId, false, body);
    }

    private MqttInboundMessage conversationEnded(
        String eventId,
        UUID scenarioId,
        UUID conversationId,
        String outcome,
        String reasonCode
    ) {
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("outcome", outcome);
        if (reasonCode == null) {
            payload.putNull("reasonCode");
        } else {
            payload.put("reasonCode", reasonCode);
        }
        return message(MqttInboundCategory.ROBOT_EVENT, "CONVERSATION_ENDED", DEVICE_ID, eventId,
            scenarioId, conversationId, null, false, body);
    }

    private MqttInboundMessage ambientObserved(String eventId, double temperatureC) {
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("temperatureC", temperatureC);
        payload.put("humidityPercent", 50.0);
        return message(MqttInboundCategory.IOT_EVENT, "AMBIENT_ENVIRONMENT_OBSERVED",
            AMBIENT_SENSOR_ID, eventId, null, null, null, false, body);
    }

    private MqttInboundMessage restState(String eventId, String state) {
        ObjectNode body = objectMapper.createObjectNode();
        body.putObject("payload").put("restState", state);
        return message(MqttInboundCategory.ROBOT_STATUS, "REST_STATE_CHANGED", DEVICE_ID, eventId,
            null, null, null, false, body);
    }

    private static final class RecordingRobotPublisher implements RobotCommandPublisher {
        private final List<RobotCommand> commands = new ArrayList<>();

        @Override
        public void publish(RobotCommand command) {
            commands.add(command);
        }
    }

    private static final class RecordingAiPublisher implements AiConversationCommandPublisher {
        private final List<AiConversationCommand> commands = new ArrayList<>();

        @Override
        public void publish(AiConversationCommand command) {
            commands.add(command);
        }
    }
}
