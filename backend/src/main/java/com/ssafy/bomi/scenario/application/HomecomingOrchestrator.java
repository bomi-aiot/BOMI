package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Drives the HOMECOMING scenario happy path across the robot boundary.
 *
 * <p>Flow: door opened → create scenario + NAVIGATE(entrance) → robot arrives →
 * SPEAK(greeting) + hand off to conversation → conversation ends →
 * NAVIGATE(default) → robot arrives → COMPLETED.</p>
 *
 * <p>All state transitions are guarded by the {@link Scenario} state machine, and
 * each method is transactional so a failed step rolls back (the dispatcher then
 * allows a redelivery to retry). Robot mode co-transition and rest/environment
 * observations are handled by a separate ticket.</p>
 */
@Service
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class HomecomingOrchestrator {

    private static final Logger log = LoggerFactory.getLogger(HomecomingOrchestrator.class);
    private static final Duration COMMAND_TTL = Duration.ofMinutes(2);
    private static final String DEFAULT_GREETING = "어서 오세요, 잘 다녀오셨어요?";

    private final ScenarioRepository scenarioRepository;
    private final RobotRepository robotRepository;
    private final RobotCommandPublisher commandPublisher;
    private final ConversationGateway conversationGateway;
    private final HomecomingProperties properties;

    public HomecomingOrchestrator(
        ScenarioRepository scenarioRepository,
        RobotRepository robotRepository,
        RobotCommandPublisher commandPublisher,
        ConversationGateway conversationGateway,
        HomecomingProperties properties
    ) {
        this.scenarioRepository = scenarioRepository;
        this.robotRepository = robotRepository;
        this.commandPublisher = commandPublisher;
        this.conversationGateway = conversationGateway;
        this.properties = properties;
    }

    /** Door opened: open a HOMECOMING scenario and send the robot to the entrance. */
    @Transactional
    public void startHomecoming(String sensorId) {
        UUID seniorId = properties.resolveSenior(sensorId);
        Robot robot = robotRepository.findBySeniorId(seniorId)
            .orElseThrow(() -> new IllegalStateException("No robot assigned to senior: " + seniorId));

        Scenario scenario = Scenario.create(seniorId, robot.getId(), ScenarioType.HOMECOMING, sensorId);
        scenario.beginMovingToEntrance();
        scenarioRepository.save(scenario);

        publishNavigate(scenario.getId(), robot, HomecomingContract.TARGET_ENTRANCE);
        log.info("Homecoming started: scenarioId={}, seniorId={}, robot={}",
            scenario.getId(), seniorId, robot.getDeviceId());
    }

    /** Robot reported arrival for a scenario (result echoes the scenarioId). */
    @Transactional
    public void onRobotArrived(UUID scenarioId) {
        Scenario scenario = scenarioRepository.findById(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("Arrival for unknown scenario; ignoring: scenarioId={}", scenarioId);
            return;
        }

        switch (scenario.getFinalStatus()) {
            case MOVING_TO_ENTRANCE -> {
                Robot robot = requireRobot(scenario.getRobotId());
                scenario.checkInteraction();
                publishSpeak(scenario.getId(), robot, DEFAULT_GREETING);
                scenario.beginConversation();
                scenarioRepository.save(scenario);
                conversationGateway.startConversation(scenario.getId(), scenario.getSeniorId());
            }
            case RETURNING_TO_DEFAULT -> {
                scenario.complete();
                scenarioRepository.save(scenario);
                log.info("Homecoming completed: scenarioId={}", scenario.getId());
            }
            default -> log.warn("Arrival ignored for scenario in status {}: scenarioId={}",
                scenario.getFinalStatus(), scenario.getId());
        }
    }

    /** Conversation finished (called by the voice side): send the robot back home. */
    @Transactional
    public void onConversationEnded(UUID scenarioId) {
        Scenario scenario = scenarioRepository.findById(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("Conversation end for unknown scenario; ignoring: scenarioId={}", scenarioId);
            return;
        }
        Robot robot = requireRobot(scenario.getRobotId());
        scenario.decideReturn();
        scenario.returnToDefault();
        scenarioRepository.save(scenario);
        publishNavigate(scenario.getId(), robot, HomecomingContract.TARGET_DEFAULT);
    }

    private Robot requireRobot(UUID robotId) {
        return robotRepository.findById(robotId)
            .orElseThrow(() -> new IllegalStateException("Scenario references unknown robot: " + robotId));
    }

    private void publishNavigate(UUID scenarioId, Robot robot, String target) {
        publish(scenarioId, robot, RobotCommandType.NAVIGATE,
            Map.of(HomecomingContract.NAV_TARGET_KEY, target));
    }

    private void publishSpeak(UUID scenarioId, Robot robot, String text) {
        publish(scenarioId, robot, RobotCommandType.SPEAK,
            Map.of(HomecomingContract.SPEAK_TEXT_KEY, text));
    }

    private void publish(UUID scenarioId, Robot robot, RobotCommandType type, Map<String, Object> payload) {
        if (robot.getDeviceId() == null) {
            throw new IllegalStateException("Robot has no deviceId; cannot address command: " + robot.getId());
        }
        OffsetDateTime now = OffsetDateTime.now();
        RobotCommand command = new RobotCommand(
            UUID.randomUUID().toString(),
            scenarioId,
            robot.getDeviceId(),
            type,
            now,
            now.plus(COMMAND_TTL),
            payload
        );
        commandPublisher.publish(command);
    }
}
