package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.conversation.domain.ConversationOutcome;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.mqtt.inbound.MqttContractViolationException;
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
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Drives the shared movement and AI conversation lifecycle for supported scenarios. */
@Service
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class HomecomingOrchestrator {

    public static final String REASON_AI_START_TIMEOUT = "AI_START_TIMEOUT";
    public static final String REASON_CONVERSATION_TIMEOUT = "CONVERSATION_TIMEOUT";

    static final String DEFAULT_GREETING = "어서 오세요. 오늘 외출은 어떠셨어요?";

    private static final Logger log = LoggerFactory.getLogger(HomecomingOrchestrator.class);
    private static final Duration ROBOT_COMMAND_TTL = Duration.ofMinutes(2);

    private final ScenarioRepository scenarioRepository;
    private final ConversationRepository conversationRepository;
    private final RobotRepository robotRepository;
    private final RobotCommandPublisher commandPublisher;
    private final ConversationGateway conversationGateway;
    private final HomecomingProperties properties;
    private final ScenarioRobotStartPolicy startPolicy;
    private final Clock clock;

    public HomecomingOrchestrator(
        ScenarioRepository scenarioRepository,
        ConversationRepository conversationRepository,
        RobotRepository robotRepository,
        RobotCommandPublisher commandPublisher,
        ConversationGateway conversationGateway,
        HomecomingProperties properties,
        ScenarioRobotStartPolicy startPolicy,
        Clock clock
    ) {
        this.scenarioRepository = scenarioRepository;
        this.conversationRepository = conversationRepository;
        this.robotRepository = robotRepository;
        this.commandPublisher = commandPublisher;
        this.conversationGateway = conversationGateway;
        this.properties = properties;
        this.startPolicy = startPolicy;
        this.clock = clock;
    }

    /** Starts a generic homecoming greeting for a mapped door sensor. */
    @Transactional
    public void startHomecoming(String sensorId) {
        UUID seniorId = properties.findSenior(sensorId).orElse(null);
        if (seniorId == null) {
            log.warn("Door event from unmapped sensor; dropping: sensorId={}", sensorId);
            return;
        }
        startHomecoming(seniorId, sensorId, DEFAULT_GREETING);
    }

    /** Stores the greeting snapshot, then sends only NAVIGATE(ENTRANCE). */
    @Transactional
    public void startHomecoming(UUID seniorId, String sensorId, String greeting) {
        if (greeting == null || greeting.isBlank()) {
            log.info("Homecoming without a greeting was ignored: seniorId={}", seniorId);
            return;
        }
        var admission = startPolicy.admitBySenior(
            seniorId,
            ScenarioType.HOMECOMING,
            Duration.ZERO,
            ScenarioRobotStartPolicy.ModePolicy.IDLE_ONLY);
        if (!admission.allowed()) {
            log.info("Homecoming suppressed ({}): seniorId={}",
                admission.blockReason(), seniorId);
            return;
        }
        Robot robot = admission.robot();

        Scenario scenario = Scenario.create(
            seniorId, robot.getId(), ScenarioType.HOMECOMING, sensorId);
        scenario.prepareConversation(
            ConversationIntent.HOMECOMING_GREETING,
            greeting,
            homecomingContext(sensorId));
        scenario.beginMovingToEntrance();
        enqueueNavigate(scenario, robot, HomecomingContract.TARGET_ENTRANCE);
        syncRobotMode(robot, scenario);

        log.info("Homecoming started: scenarioId={}, seniorId={}, robot={}",
            scenario.getId(), seniorId, robot.getDeviceId());
    }

    /** Compatibility overload for tests and internal calls without a source device. */
    @Transactional
    public void onRobotArrived(UUID scenarioId) {
        onRobotArrived(scenarioId, null, null, true);
    }

    /** Handles arrival at either the scenario destination or DEFAULT. */
    @Transactional
    public void onRobotArrived(UUID scenarioId, String sourceRobotId) {
        onRobotArrived(scenarioId, sourceRobotId, null, true);
    }

    /** Handles a correlated v1 result; legacy results are the only commandId exception. */
    @Transactional
    public void onRobotArrived(
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        boolean legacyContract
    ) {
        Scenario scenario = scenarioRepository.findByIdForUpdate(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("Arrival for unknown scenario; ignoring: scenarioId={}", scenarioId);
            return;
        }
        Robot robot = requireRobot(scenario.getRobotId());
        requireMatchingRobot(robot, sourceRobotId);

        switch (scenario.getFinalStatus()) {
            case MOVING_TO_ENTRANCE -> {
                acceptNavigationResult(
                    scenario, commandId, legacyContract, initialNavigationTarget(scenario));
                scenario.checkInteraction();
                scenarioRepository.save(scenario);
                syncRobotMode(robot, scenario);

                ConversationStartResult result = conversationGateway.startConversation(scenarioId);
                if (!result.published()) {
                    beginReturnToDefault(scenario, robot);
                }
            }
            case RETURNING_TO_DEFAULT -> {
                acceptNavigationResult(
                    scenario, commandId, legacyContract, HomecomingContract.TARGET_DEFAULT);
                finishAfterSuccessfulReturn(scenario, robot);
            }
            default -> log.warn("Arrival ignored for scenario in status {}: scenarioId={}",
                scenario.getFinalStatus(), scenario.getId());
        }
    }

    @Transactional
    public void onNavigationFailed(UUID scenarioId) {
        onNavigationFailed(scenarioId, null);
    }

    @Transactional
    public void onNavigationFailed(UUID scenarioId, String sourceRobotId) {
        terminateNavigation(scenarioId, sourceRobotId, null, true, ScenarioStatus.FAILED);
    }

    @Transactional
    public void onNavigationFailed(
        UUID scenarioId, String sourceRobotId, String commandId, boolean legacyContract
    ) {
        terminateNavigation(
            scenarioId, sourceRobotId, commandId, legacyContract, ScenarioStatus.FAILED);
    }

    @Transactional
    public void onNavigationCancelled(UUID scenarioId, String sourceRobotId) {
        terminateNavigation(scenarioId, sourceRobotId, null, true, ScenarioStatus.CANCELLED);
    }

    @Transactional
    public void onNavigationCancelled(
        UUID scenarioId, String sourceRobotId, String commandId, boolean legacyContract
    ) {
        terminateNavigation(
            scenarioId, sourceRobotId, commandId, legacyContract, ScenarioStatus.CANCELLED);
    }

    @Transactional
    public void onNavigationTimedOut(UUID scenarioId, String sourceRobotId) {
        terminateNavigation(scenarioId, sourceRobotId, null, true, ScenarioStatus.TIMED_OUT);
    }

    @Transactional
    public void onNavigationTimedOut(
        UUID scenarioId, String sourceRobotId, String commandId, boolean legacyContract
    ) {
        terminateNavigation(
            scenarioId, sourceRobotId, commandId, legacyContract, ScenarioStatus.TIMED_OUT);
    }

    /** AI accepted the command and is ready to listen. */
    @Transactional
    public void onConversationStarted(
        UUID scenarioId,
        UUID conversationId,
        String commandId,
        String sourceRobotId,
        ConversationIntent intent,
        OffsetDateTime occurredAt
    ) {
        Scenario scenario = requireScenarioForUpdate(scenarioId);
        Robot robot = requireRobot(scenario.getRobotId());
        requireMatchingRobot(robot, sourceRobotId);
        Conversation conversation = requireConversation(conversationId, scenario, commandId);

        if (!conversation.isOpen() || conversation.hasAiStarted()) {
            log.info("Duplicate/late CONVERSATION_STARTED ignored: conversationId={}", conversationId);
            return;
        }
        if (scenario.getFinalStatus() != ScenarioStatus.CHECKING_INTERACTION) {
            log.warn("CONVERSATION_STARTED ignored for scenario in status {}: scenarioId={}",
                scenario.getFinalStatus(), scenarioId);
            return;
        }
        ConversationIntent expected = scenario.requirePreparedConversation().intent();
        if (expected != intent) {
            throw new MqttContractViolationException(
                "CONVERSATION_STARTED intent does not match scenario request");
        }

        conversation.markAiStarted(occurredAt);
        conversationRepository.save(conversation);
        scenario.beginConversation();
        scenarioRepository.save(scenario);
        syncRobotMode(robot, scenario);
        log.info("AI conversation started: scenarioId={}, conversationId={}",
            scenarioId, conversationId);
    }

    /** AI reported a terminal result; all results first return the robot to DEFAULT. */
    @Transactional
    public void onConversationEnded(
        UUID scenarioId,
        UUID conversationId,
        String sourceRobotId,
        ConversationOutcome outcome,
        String reasonCode,
        OffsetDateTime occurredAt
    ) {
        Scenario scenario = requireScenarioForUpdate(scenarioId);
        Robot robot = requireRobot(scenario.getRobotId());
        requireMatchingRobot(robot, sourceRobotId);
        Conversation conversation = requireConversation(conversationId, scenario, null);

        if (!conversation.end(outcome, reasonCode, occurredAt)) {
            log.info("Duplicate/late CONVERSATION_ENDED ignored: conversationId={}", conversationId);
            return;
        }
        conversationRepository.save(conversation);
        if (scenario.getFinalStatus() == ScenarioStatus.CHECKING_INTERACTION
            || scenario.getFinalStatus() == ScenarioStatus.CONVERSING) {
            beginReturnToDefault(scenario, robot);
        } else {
            log.warn("Conversation ended after scenario left dialogue states: scenarioId={}, status={}",
                scenarioId, scenario.getFinalStatus());
        }
    }

    /** Called by the 10-second watchdog for a command AI did not acknowledge. */
    @Transactional
    public void onConversationStartTimedOut(UUID conversationId) {
        timeOutConversation(conversationId, false, REASON_AI_START_TIMEOUT);
    }

    /** Called by the five-minute watchdog for a conversation that did not end. */
    @Transactional
    public void onConversationActiveTimedOut(UUID conversationId) {
        timeOutConversation(conversationId, true, REASON_CONVERSATION_TIMEOUT);
    }

    private void timeOutConversation(UUID conversationId, boolean mustHaveStarted, String reasonCode) {
        UUID scenarioId = conversationRepository.findScenarioIdById(conversationId).orElse(null);
        if (scenarioId == null) {
            return;
        }

        // Every conversation lifecycle writer uses Scenario -> Robot -> Conversation.
        // The scalar lookup above avoids attaching a stale Conversation before its turn to lock.
        Scenario scenario = requireScenarioForUpdate(scenarioId);
        Robot robot = requireRobot(scenario.getRobotId());
        Conversation conversation = conversationRepository.findByIdForUpdate(conversationId)
            .orElse(null);
        if (conversation == null || !conversation.isOpen()
            || conversation.hasAiStarted() != mustHaveStarted) {
            return;
        }
        ScenarioStatus expected = mustHaveStarted
            ? ScenarioStatus.CONVERSING : ScenarioStatus.CHECKING_INTERACTION;
        if (scenario.getFinalStatus() != expected) {
            return;
        }

        conversation.end(ConversationOutcome.FAILED, reasonCode, OffsetDateTime.now(clock));
        conversationRepository.save(conversation);
        beginReturnToDefault(scenario, robot);
        log.warn("AI conversation timed out; returning to DEFAULT: scenarioId={}, "
            + "conversationId={}, reasonCode={}", scenario.getId(), conversationId, reasonCode);
    }

    private void beginReturnToDefault(Scenario scenario, Robot robot) {
        if (robot.getCurrentMode() == RobotMode.SAFE_STOP) {
            scenario.fail(null, "SAFETY_STOP");
            scenarioRepository.save(scenario);
            log.warn("Return movement suppressed while Robot is SAFE_STOP: scenarioId={}",
                scenario.getId());
            return;
        }
        scenario.decideReturn();
        scenario.returnToDefault();
        enqueueNavigate(scenario, robot, HomecomingContract.TARGET_DEFAULT);
        syncRobotMode(robot, scenario);
    }

    private void finishAfterSuccessfulReturn(Scenario scenario, Robot robot) {
        Conversation conversation = conversationRepository.findByScenarioId(scenario.getId()).orElse(null);
        if (conversation == null || conversation.getEndOutcome() == null
            || conversation.getEndOutcome() == ConversationOutcome.COMPLETED
            || conversation.getEndOutcome() == ConversationOutcome.NO_RESPONSE) {
            scenario.complete();
        } else if (conversation.getEndOutcome() == ConversationOutcome.CANCELLED) {
            scenario.cancel();
        } else if (isBackendTimeout(conversation.getReasonCode())) {
            scenario.timeOut();
        } else {
            scenario.fail();
        }
        scenarioRepository.save(scenario);

        // The robot physically reached DEFAULT, so AI failure alone must not leave SAFE_STOP.
        // A physical SAFE_STOP or a rest observation made while the scenario was active is
        // independent of this logical completion and must never be cleared here.
        if (robot.getCurrentMode() == RobotMode.SCENARIO_ACTIVE) {
            robot.changeMode(RobotMode.IDLE);
            robotRepository.save(robot);
        }
        log.info("Scenario finished after DEFAULT return: scenarioId={}, type={}, status={}",
            scenario.getId(), scenario.getScenarioType(), scenario.getFinalStatus());
    }

    private void terminateNavigation(
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        boolean legacyContract,
        ScenarioStatus terminalStatus
    ) {
        Scenario scenario = scenarioRepository.findByIdForUpdate(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("Navigation result for unknown scenario; ignoring: scenarioId={}", scenarioId);
            return;
        }
        if (scenario.isTerminated()) {
            log.info("Late navigation result ignored: scenarioId={}, status={}",
                scenarioId, scenario.getFinalStatus());
            return;
        }
        Robot robot = requireRobot(scenario.getRobotId());
        requireMatchingRobot(robot, sourceRobotId);
        String expectedTarget;
        if (scenario.getFinalStatus() == ScenarioStatus.MOVING_TO_ENTRANCE) {
            expectedTarget = initialNavigationTarget(scenario);
        } else if (scenario.getFinalStatus() == ScenarioStatus.RETURNING_TO_DEFAULT) {
            expectedTarget = HomecomingContract.TARGET_DEFAULT;
        } else {
            log.warn("Navigation terminal result ignored without active navigation: "
                    + "scenarioId={}, status={}", scenarioId, scenario.getFinalStatus());
            return;
        }
        acceptNavigationResult(scenario, commandId, legacyContract, expectedTarget);
        switch (terminalStatus) {
            case FAILED -> scenario.fail();
            case CANCELLED -> scenario.cancel();
            case TIMED_OUT -> scenario.timeOut();
            default -> throw new IllegalArgumentException("Not a navigation terminal status");
        }
        scenarioRepository.save(scenario);
        syncRobotMode(robot, scenario);
        log.warn("Navigation ended scenario: scenarioId={}, status={}", scenarioId, terminalStatus);
    }

    private Scenario requireScenarioForUpdate(UUID scenarioId) {
        return scenarioRepository.findByIdForUpdate(scenarioId)
            .orElseThrow(() -> new MqttContractViolationException(
                "MQTT event references unknown scenarioId=" + scenarioId));
    }

    private Conversation requireConversation(
        UUID conversationId,
        Scenario scenario,
        String expectedCommandId
    ) {
        Conversation conversation = conversationRepository.findByIdForUpdate(conversationId)
            .orElseThrow(() -> new MqttContractViolationException(
                "MQTT event references unknown conversationId=" + conversationId));
        if (!scenario.getId().equals(conversation.getScenarioId())
            || !scenario.getSeniorId().equals(conversation.getSeniorId())) {
            throw new MqttContractViolationException(
                "Conversation does not belong to the referenced scenario");
        }
        if (expectedCommandId != null
            && !expectedCommandId.equals(conversation.getStartCommandId())) {
            throw new MqttContractViolationException(
                "CONVERSATION_STARTED commandId does not match START_CONVERSATION");
        }
        return conversation;
    }

    private Robot requireRobot(UUID robotId) {
        return robotRepository.findByIdForUpdate(robotId)
            .orElseThrow(() -> new IllegalStateException(
                "Scenario references unknown robot: " + robotId));
    }

    private static void requireMatchingRobot(Robot robot, String sourceRobotId) {
        if (sourceRobotId != null && !sourceRobotId.equals(robot.getDeviceId())) {
            throw new MqttContractViolationException(
                "MQTT robotId does not match the robot assigned to scenario");
        }
    }

    private void syncRobotMode(Robot robot, Scenario scenario) {
        RobotMode desired = RobotModePolicy.forScenario(scenario.getFinalStatus());
        if (desired == RobotMode.SAFE_STOP) {
            robot.changeMode(RobotMode.SAFE_STOP);
            robotRepository.save(robot);
            return;
        }
        if (desired == RobotMode.IDLE) {
            if (robot.getCurrentMode() == RobotMode.SCENARIO_ACTIVE) {
                robot.changeMode(RobotMode.IDLE);
                robotRepository.save(robot);
            }
            return;
        }
        if (robot.getCurrentMode() == RobotMode.IDLE) {
            robot.changeMode(RobotMode.SCENARIO_ACTIVE);
            robotRepository.save(robot);
        }
    }

    private void enqueueNavigate(Scenario scenario, Robot robot, String target) {
        if (robot.getDeviceId() == null) {
            throw new IllegalStateException(
                "Robot has no deviceId; cannot address command: " + robot.getId());
        }
        OffsetDateTime now = OffsetDateTime.now(clock);
        String commandId = UUID.randomUUID().toString();
        scenario.expectNavigationResult(commandId, target);
        scenarioRepository.save(scenario);
        commandPublisher.publish(new RobotCommand(
            commandId,
            scenario.getId(),
            robot.getDeviceId(),
            RobotCommandType.NAVIGATE,
            now,
            now.plus(ROBOT_COMMAND_TTL),
            Map.of(HomecomingContract.NAV_TARGET_KEY, target)));
    }

    private static void acceptNavigationResult(
        Scenario scenario,
        String commandId,
        boolean legacyContract,
        String expectedTarget
    ) {
        if (scenario.getActiveNavigationCommandId() == null
            || scenario.getActiveNavigationTarget() == null) {
            throw new MqttContractViolationException(
                "Scenario has no active NAVIGATE command");
        }
        if (!expectedTarget.equals(scenario.getActiveNavigationTarget())) {
            throw new IllegalStateException(
                "Scenario navigation target does not match its current state");
        }
        if (!legacyContract && !scenario.getActiveNavigationCommandId().equals(commandId)) {
            throw new MqttContractViolationException(
                "NAVIGATION_RESULT commandId does not match the active NAVIGATE command");
        }
        scenario.clearExpectedNavigationResult();
    }

    private static Map<String, Object> homecomingContext(String sensorId) {
        Map<String, Object> context = new LinkedHashMap<>();
        if (sensorId != null && !sensorId.isBlank()) {
            context.put("sourceId", sensorId);
        }
        context.put("location", HomecomingContract.TARGET_ENTRANCE);
        return context;
    }

    private static boolean isBackendTimeout(String reasonCode) {
        return REASON_AI_START_TIMEOUT.equals(reasonCode)
            || REASON_CONVERSATION_TIMEOUT.equals(reasonCode);
    }

    private static String initialNavigationTarget(Scenario scenario) {
        return scenario.getScenarioType() == ScenarioType.HOMECOMING
            ? HomecomingContract.TARGET_ENTRANCE
            : HomecomingContract.TARGET_LIVING_ROOM;
    }
}
