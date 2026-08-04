package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
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
    /**
     * 방향을 판정하지 못했을 때의 인사.
     *
     * <p>S15P11E102-226 이전에는 모든 문 열림에 이 문장이 나갔다. 지금은 방향을
     * 판정한 경우 {@code GreetingDecider} 가 고른 문장이 대신 쓰이고, 이 값은 방향을
     * 알 수 없는 통과의 폴백이다 — 어르신인지 방문자인지 모를 때는 정보를 얹지 않고
     * 인사만 한다.</p>
     */
    static final String DEFAULT_GREETING = "어서 오세요, 잘 다녀오셨어요?";

    private final ScenarioRepository scenarioRepository;
    private final RobotRepository robotRepository;
    private final RobotCommandPublisher commandPublisher;
    private final ConversationGateway conversationGateway;
    private final HomecomingProperties properties;
    private final ScenarioStartGuard startGuard;

    public HomecomingOrchestrator(
        ScenarioRepository scenarioRepository,
        RobotRepository robotRepository,
        RobotCommandPublisher commandPublisher,
        ConversationGateway conversationGateway,
        HomecomingProperties properties,
        ScenarioStartGuard startGuard
    ) {
        this.scenarioRepository = scenarioRepository;
        this.robotRepository = robotRepository;
        this.commandPublisher = commandPublisher;
        this.conversationGateway = conversationGateway;
        this.properties = properties;
        this.startGuard = startGuard;
    }

    /**
     * Door opened with no direction known: greet without adding information.
     *
     * <p>Kept for the MQTT path that still sends a bare {@code DOOR_OPENED}. When the
     * direction <em>is</em> resolved (S15P11E102-226), the caller passes the sentence
     * {@code GreetingDecider} chose instead.</p>
     */
    @Transactional
    public void startHomecoming(String sensorId) {
        UUID seniorId = properties.findSenior(sensorId).orElse(null);
        if (seniorId == null) {
            // 예외를 던지면 ack 가 생략되어 브로커가 무한 재전송한다. 경고 후 폐기.
            log.warn("Door event from unmapped sensor; dropping: sensorId={}", sensorId);
            return;
        }
        startHomecoming(seniorId, sensorId, DEFAULT_GREETING);
    }

    /**
     * Opens a HOMECOMING scenario, sends the robot to the entrance, and speaks.
     *
     * <p><b>Speech is published here, not on arrival</b> (S15P11E102-226). It used to wait
     * for {@code onRobotArrived}, which meant a slow or failed navigation swallowed the
     * greeting entirely — and the greeting has a ~45 second deadline, shorter than a
     * navigation that has to route around a chair. Voice carries across rooms; there is no
     * reason it should wait for wheels (CLAUDE.md §11).</p>
     *
     * <p>The move command still goes out immediately. The two are simply independent now:
     * one failing no longer silences the other.</p>
     *
     * @param greeting the single sentence chosen by {@code GreetingDecider}, or null to
     *     move without speaking — a delivery, or a passage we could not read
     */
    @Transactional
    public void startHomecoming(UUID seniorId, String sensorId, String greeting) {
        // 문 열림은 이산 사건이므로 쿨다운 없음(Duration.ZERO) — 30분에 두 번 귀가는
        // 정상이다. 활성 시나리오 검사만 적용: 이미 다른 시나리오가 돌고 있으면
        // 로봇이 두 명령 사이에서 찢어지므로 이번 인사는 조용히 접는다.
        var blocked = startGuard.check(seniorId, ScenarioType.HOMECOMING, Duration.ZERO);
        if (blocked.isPresent()) {
            log.info("Homecoming suppressed ({}): seniorId={}", blocked.get(), seniorId);
            return;
        }

        Robot robot = robotRepository.findBySeniorId(seniorId).orElse(null);
        if (robot == null) {
            // 예외를 던지면 ack 가 생략되어 브로커가 무한 재전송한다(A-3과 같은 원리).
            // 로봇 미배정은 재전송으로 해결되는 문제가 아니므로 경고 후 폐기한다.
            log.warn("No robot assigned to senior; dropping homecoming: seniorId={}", seniorId);
            return;
        }

        Scenario scenario = Scenario.create(seniorId, robot.getId(), ScenarioType.HOMECOMING, sensorId);
        scenario.beginMovingToEntrance();
        scenarioRepository.save(scenario);
        syncRobotMode(robot, scenario);

        publishNavigate(scenario.getId(), robot, HomecomingContract.TARGET_ENTRANCE);
        if (greeting != null && !greeting.isBlank()) {
            publishSpeak(scenario.getId(), robot, greeting);
        }
        log.info("Homecoming started: scenarioId={}, seniorId={}, robot={}, spoke={}",
            scenario.getId(), seniorId, robot.getDeviceId(), greeting != null);
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
                // 인사는 startHomecoming 에서 이미 나갔다 (S15P11E102-226). 여기서 다시
                // 말하면 어르신은 같은 인사를 두 번 듣고, 두 번째는 로봇이 도착한 뒤라
                // 한참 늦다. 도착 시점에 하는 일은 대화로 넘기는 것뿐이다.
                scenario.beginConversation();
                scenarioRepository.save(scenario);
                syncRobotMode(robot, scenario);
                conversationGateway.startConversation(scenario.getId(), scenario.getSeniorId());
            }
            case RETURNING_TO_DEFAULT -> {
                Robot robot = requireRobot(scenario.getRobotId());
                scenario.complete();
                scenarioRepository.save(scenario);
                syncRobotMode(robot, scenario);
                log.info("Homecoming completed: scenarioId={}", scenario.getId());
            }
            default -> log.warn("Arrival ignored for scenario in status {}: scenarioId={}",
                scenario.getFinalStatus(), scenario.getId());
        }
    }

    /**
     * Robot reported a navigation failure (e.g. PATH_BLOCKED): stop the scenario.
     *
     * <p>Fails the scenario and forces the robot to {@code SAFE_STOP}. Unknown or
     * already-terminated scenarios are ignored so a duplicate or late failure
     * stays idempotent.</p>
     */
    @Transactional
    public void onNavigationFailed(UUID scenarioId) {
        Scenario scenario = scenarioRepository.findById(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("Navigation failure for unknown scenario; ignoring: scenarioId={}", scenarioId);
            return;
        }
        if (scenario.isTerminated()) {
            log.warn("Navigation failure ignored for already-terminated scenario {}: scenarioId={}",
                scenario.getFinalStatus(), scenario.getId());
            return;
        }
        Robot robot = requireRobot(scenario.getRobotId());
        scenario.fail();
        scenarioRepository.save(scenario);
        syncRobotMode(robot, scenario);
        log.warn("Navigation failed; scenario marked FAILED: scenarioId={}", scenario.getId());
    }

    /** Conversation finished (called by the voice side): send the robot back home. */
    @Transactional
    public void onConversationEnded(UUID scenarioId) {
        Scenario scenario = scenarioRepository.findById(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("Conversation end for unknown scenario; ignoring: scenarioId={}", scenarioId);
            return;
        }
        if (scenario.getFinalStatus() != ScenarioStatus.CONVERSING) {
            // Late or duplicate signal (or wrong state): stay idempotent, do not re-drive.
            log.warn("Conversation end ignored for scenario in status {}: scenarioId={}",
                scenario.getFinalStatus(), scenario.getId());
            return;
        }
        Robot robot = requireRobot(scenario.getRobotId());
        scenario.decideReturn();
        scenario.returnToDefault();
        scenarioRepository.save(scenario);
        syncRobotMode(robot, scenario);
        publishNavigate(scenario.getId(), robot, HomecomingContract.TARGET_DEFAULT);
    }

    /** Keeps the robot mode in step with the scenario status (SCENARIO_ACTIVE/IDLE/SAFE_STOP). */
    private void syncRobotMode(Robot robot, Scenario scenario) {
        robot.changeMode(RobotModePolicy.forScenario(scenario.getFinalStatus()));
        robotRepository.save(robot);
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
