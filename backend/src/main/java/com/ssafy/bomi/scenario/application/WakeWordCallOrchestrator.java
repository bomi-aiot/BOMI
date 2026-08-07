package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.mqtt.inbound.MqttContractViolationException;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.domain.WakeWordTriggerDisposition;
import com.ssafy.bomi.scenario.domain.WakeWordTriggerReceipt;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.scenario.repository.WakeWordTriggerReceiptRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Owns only the Backend movement lifecycle for an AI-initiated wake-word call. */
@Service
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class WakeWordCallOrchestrator {

    private static final Logger log = LoggerFactory.getLogger(WakeWordCallOrchestrator.class);
    private static final Duration COMMAND_TTL = Duration.ofMinutes(2);

    private final ScenarioRepository scenarioRepository;
    private final WakeWordTriggerReceiptRepository receiptRepository;
    private final RobotRepository robotRepository;
    private final RobotCommandPublisher commandPublisher;
    private final ScenarioRobotStartPolicy startPolicy;
    private final Clock clock;

    public WakeWordCallOrchestrator(
        ScenarioRepository scenarioRepository,
        WakeWordTriggerReceiptRepository receiptRepository,
        RobotRepository robotRepository,
        RobotCommandPublisher commandPublisher,
        ScenarioRobotStartPolicy startPolicy,
        Clock clock
    ) {
        this.scenarioRepository = scenarioRepository;
        this.receiptRepository = receiptRepository;
        this.robotRepository = robotRepository;
        this.commandPublisher = commandPublisher;
        this.startPolicy = startPolicy;
        this.clock = clock;
    }

    /** Accepts the AI trigger and publishes exactly one movement command when allowed. */
    @Transactional
    public void onWakeWordDetected(
        String robotDeviceId,
        String eventId,
        OffsetDateTime occurredAt,
        String keyword,
        Double confidence
    ) {
        requireText(robotDeviceId, "robotDeviceId");
        requireText(eventId, "eventId");
        requireText(keyword, "keyword");
        if (occurredAt == null) {
            throw new IllegalArgumentException("occurredAt must not be null");
        }

        WakeWordTriggerReceipt previous = receiptRepository.findById(eventId).orElse(null);
        if (previous != null) {
            acceptDuplicate(previous, robotDeviceId, occurredAt, keyword, confidence);
            return;
        }

        var admission = startPolicy.admitByDevice(
            robotDeviceId,
            ScenarioType.WAKE_WORD_CALL,
            Duration.ZERO,
            ScenarioRobotStartPolicy.ModePolicy.IDLE_OR_REST_GUARD);

        // A transaction may have committed while this one waited for the senior lock.
        previous = receiptRepository.findById(eventId).orElse(null);
        if (previous != null) {
            acceptDuplicate(previous, robotDeviceId, occurredAt, keyword, confidence);
            return;
        }

        WakeWordTriggerReceipt receipt = claimReceipt(
            eventId, robotDeviceId, occurredAt, keyword, confidence);
        if (!admission.allowed()) {
            receipt.reject(wakeDisposition(admission.blockReason()));
            log.warn("Wake-word movement suppressed ({}): robotId={}, eventId={}",
                admission.blockReason(), robotDeviceId, eventId);
            return;
        }
        Robot robot = admission.robot();
        UUID seniorId = robot.getSeniorId();

        Scenario scenario = Scenario.create(
            seniorId, robot.getId(), ScenarioType.WAKE_WORD_CALL, eventId);
        scenario.recordTriggerContext(triggerContext(
            robotDeviceId, occurredAt, keyword, confidence));
        scenario.beginNavigation();
        scenarioRepository.save(scenario);

        OffsetDateTime now = OffsetDateTime.now(clock);
        String commandId = UUID.randomUUID().toString();
        scenario.expectNavigationResult(commandId, HomecomingContract.TARGET_LIVING_ROOM);
        // Flush before registering the after-commit publish. A DB idempotency conflict
        // must abort without ever scheduling a duplicate physical command.
        scenarioRepository.saveAndFlush(scenario);
        receipt.accept(scenario.getId());

        if (robot.getCurrentMode() == RobotMode.IDLE) {
            robot.changeMode(RobotMode.SCENARIO_ACTIVE);
            robotRepository.save(robot);
        }

        // FOLLOW_START, not NAVIGATE: the robot no longer drives to a fixed
        // living-room waypoint. It turns in place towards the sound, finds the
        // senior with its camera and closes the last few steps itself. Backend
        // only says *when* to start that.
        //
        // The command carries no payload. The direction cannot travel in this
        // contract — MqttInboundMessageParser whitelists WAKE_WORD_DETECTED
        // payload fields to keyword/confidence — so the robot sends the angle to
        // itself over an internal UDP channel instead.
        commandPublisher.publish(new RobotCommand(
            commandId,
            scenario.getId(),
            robotDeviceId,
            RobotCommandType.FOLLOW_START,
            now,
            now.plus(COMMAND_TTL),
            Map.of()));

        log.info("Wake-word call search started: scenarioId={}, seniorId={}, robotId={}, "
                + "eventId={}", scenario.getId(), seniorId, robotDeviceId, eventId);
    }

    /**
     * Applies one correlated v1 NAVIGATION_RESULT.
     *
     * <p>The wake-word call now publishes FOLLOW_START, so nothing reaches this
     * method in normal operation. It is kept as the rollback path: flipping the
     * published command type back to {@code NAVIGATE} restores the previous
     * drive-to-the-living-room behaviour with no other change. Remove it once
     * FOLLOW_START is proven on the robot.</p>
     */
    @Transactional
    public void onNavigationResult(
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        boolean legacyContract,
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        applyRobotResult(scenarioId, sourceRobotId, commandId, legacyContract,
            outcome, resultCode, reasonCode, false);
    }

    /**
     * Applies one correlated v1 FOLLOW_RESULT — the acknowledgement of FOLLOW_START.
     *
     * <p>{@code SUCCEEDED/STARTED} means the robot accepted the command and began
     * turning to look for the senior. It is not a report that anyone was found:
     * the search runs for up to ~20 seconds, which is longer than the 10 second
     * ACK timeout, so the robot answers immediately and the scenario terminates
     * here.</p>
     *
     * <p>That is also what we want operationally. Leaving the scenario NAVIGATING
     * would make the next "보미야" bounce off ACTIVE_SCENARIO_EXISTS while the
     * robot is still searching. Whether the search found anyone is deliberately
     * not reported — the robot returns to its starting heading and stops.</p>
     */
    @Transactional
    public void onFollowResult(
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        boolean legacyContract,
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        applyRobotResult(scenarioId, sourceRobotId, commandId, legacyContract,
            outcome, resultCode, reasonCode, true);
    }

    /**
     * Shared terminal-result path for both result types.
     *
     * <p>Only the result vocabulary differs: NAVIGATION uses ARRIVED/NOT_ARRIVED,
     * FOLLOW uses STARTED/UNCHANGED. Everything else — correlation checks, robot
     * identity, status guards and mode sync — is identical, and duplicating it
     * would let the two copies drift apart.</p>
     */
    private void applyRobotResult(
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        boolean legacyContract,
        String outcome,
        String resultCode,
        String reasonCode,
        boolean followVocabulary
    ) {
        String resultType = followVocabulary ? "FOLLOW_RESULT" : "NAVIGATION_RESULT";
        Scenario scenario = scenarioRepository.findByIdForUpdate(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("Wake-word {} references unknown scenario: scenarioId={}",
                resultType, scenarioId);
            return;
        }
        if (scenario.getScenarioType() != ScenarioType.WAKE_WORD_CALL) {
            throw new MqttContractViolationException(
                "Wake-word result router received a non-wake scenario");
        }
        if (legacyContract) {
            throw new MqttContractViolationException(
                "WAKE_WORD_CALL requires v1 " + resultType + " correlation fields");
        }
        if (scenario.isTerminated()) {
            log.info("Late wake-word {} ignored: scenarioId={}, status={}",
                resultType, scenarioId, scenario.getFinalStatus());
            return;
        }
        if (scenario.getFinalStatus() != ScenarioStatus.NAVIGATING) {
            log.warn("Wake-word {} ignored in status {}: scenarioId={}",
                resultType, scenario.getFinalStatus(), scenarioId);
            return;
        }

        Robot robot = robotRepository.findByIdForUpdate(scenario.getRobotId())
            .orElseThrow(() -> new IllegalStateException(
                "Wake-word scenario references unknown robot: " + scenario.getRobotId()));
        if (!Objects.equals(robot.getDeviceId(), sourceRobotId)) {
            throw new MqttContractViolationException(
                resultType + " robotId does not match wake-word scenario robot");
        }
        requireExpectedCommand(scenario, commandId);
        if (followVocabulary) {
            validateFollowResult(outcome, resultCode, reasonCode);
        } else {
            validateTerminalResult(outcome, resultCode, reasonCode);
        }

        switch (outcome) {
            case "SUCCEEDED" -> scenario.complete(resultCode, reasonCode);
            case "FAILED" -> scenario.fail(resultCode, reasonCode);
            case "CANCELLED" -> scenario.cancel(resultCode, reasonCode);
            case "TIMED_OUT" -> scenario.timeOut(resultCode, reasonCode);
            default -> throw new MqttContractViolationException(
                "Unsupported wake-word result outcome '" + outcome + "'");
        }
        scenarioRepository.save(scenario);
        syncTerminalRobotMode(robot, scenario.getFinalStatus());

        log.info("Wake-word call {} applied: scenarioId={}, status={}, resultCode={}, "
                + "reasonCode={}", resultType, scenarioId, scenario.getFinalStatus(),
            resultCode, reasonCode);
    }

    private void syncTerminalRobotMode(Robot robot, ScenarioStatus status) {
        if (status == ScenarioStatus.COMPLETED) {
            // Rest observations are orthogonal. Do not erase REST_GUARD or an external SAFE_STOP.
            if (robot.getCurrentMode() == RobotMode.SCENARIO_ACTIVE) {
                robot.changeMode(RobotMode.IDLE);
                robotRepository.save(robot);
            }
            return;
        }
        robot.changeMode(RobotMode.SAFE_STOP);
        robotRepository.save(robot);
    }

    private static void requireExpectedCommand(Scenario scenario, String commandId) {
        if (scenario.getActiveNavigationCommandId() == null
            || scenario.getActiveNavigationTarget() == null) {
            throw new MqttContractViolationException(
                "Wake-word scenario has no active NAVIGATE command");
        }
        if (!HomecomingContract.TARGET_LIVING_ROOM.equals(
                scenario.getActiveNavigationTarget())) {
            throw new MqttContractViolationException(
                "Wake-word scenario NAVIGATE target must be LIVING_ROOM");
        }
        if (!scenario.getActiveNavigationCommandId().equals(commandId)) {
            throw new MqttContractViolationException(
                "NAVIGATION_RESULT commandId does not match wake-word NAVIGATE command");
        }
    }

    private static void validateTerminalResult(
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        if ("SUCCEEDED".equals(outcome)) {
            if (!"ARRIVED".equals(resultCode) || reasonCode != null) {
                throw new MqttContractViolationException(
                    "Successful wake-word navigation must be ARRIVED with reasonCode=null");
            }
            return;
        }
        if (!"FAILED".equals(outcome)
            && !"CANCELLED".equals(outcome)
            && !"TIMED_OUT".equals(outcome)) {
            throw new MqttContractViolationException(
                "Unsupported wake-word navigation outcome '" + outcome + "'");
        }
        if (!"NOT_ARRIVED".equals(resultCode)
            || reasonCode == null || reasonCode.isBlank()) {
            throw new MqttContractViolationException(
                "Unsuccessful wake-word navigation must be NOT_ARRIVED with a reasonCode");
        }
    }

    /**
     * Enforces the FOLLOW_RESULT vocabulary (MqttInboundMessageParser is authority).
     *
     * <p>STARTED means the search began. UNCHANGED means the robot could not start
     * it at all — for example the search node is not wired up on that robot.</p>
     */
    private static void validateFollowResult(
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        if ("SUCCEEDED".equals(outcome)) {
            if (!"STARTED".equals(resultCode) || reasonCode != null) {
                throw new MqttContractViolationException(
                    "Successful wake-word follow must be STARTED with reasonCode=null");
            }
            return;
        }
        if (!"FAILED".equals(outcome)
            && !"CANCELLED".equals(outcome)
            && !"TIMED_OUT".equals(outcome)) {
            throw new MqttContractViolationException(
                "Unsupported wake-word follow outcome '" + outcome + "'");
        }
        if (!"UNCHANGED".equals(resultCode)
            || reasonCode == null || reasonCode.isBlank()) {
            throw new MqttContractViolationException(
                "Unsuccessful wake-word follow must be UNCHANGED with a reasonCode");
        }
    }

    private static Map<String, Object> triggerContext(
        String robotDeviceId,
        OffsetDateTime occurredAt,
        String keyword,
        Double confidence
    ) {
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("robotId", robotDeviceId);
        context.put("occurredAt", occurredAt.toString());
        context.put("keyword", keyword);
        if (confidence != null) {
            context.put("confidence", confidence);
        }
        return context;
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
    }

    private static WakeWordTriggerDisposition wakeDisposition(
        ScenarioRobotStartPolicy.BlockReason reason
    ) {
        return switch (reason) {
            case UNKNOWN_ROBOT, UNREGISTERED_ROBOT ->
                WakeWordTriggerDisposition.REJECTED_UNKNOWN_ROBOT;
            case INACTIVE_ROBOT -> WakeWordTriggerDisposition.REJECTED_INACTIVE_ROBOT;
            case UNASSIGNED_ROBOT -> WakeWordTriggerDisposition.REJECTED_UNASSIGNED_ROBOT;
            case SAFE_STOP -> WakeWordTriggerDisposition.REJECTED_SAFE_STOP;
            case ACTIVE_SCENARIO_EXISTS, COOLDOWN_ACTIVE ->
                WakeWordTriggerDisposition.REJECTED_ACTIVE_SCENARIO;
            case REST_GUARD, BUSY_MODE -> WakeWordTriggerDisposition.REJECTED_BUSY_MODE;
        };
    }

    private WakeWordTriggerReceipt claimReceipt(
        String eventId,
        String robotDeviceId,
        OffsetDateTime occurredAt,
        String keyword,
        Double confidence
    ) {
        return receiptRepository.saveAndFlush(WakeWordTriggerReceipt.receive(
            eventId, robotDeviceId, occurredAt, keyword, confidence));
    }

    private static void acceptDuplicate(
        WakeWordTriggerReceipt receipt,
        String robotDeviceId,
        OffsetDateTime occurredAt,
        String keyword,
        Double confidence
    ) {
        if (!receipt.describes(robotDeviceId, occurredAt, keyword, confidence)) {
            throw new MqttContractViolationException(
                "eventId was reused for a different WAKE_WORD_DETECTED trigger");
        }
        log.info("Duplicate wake-word event ignored: robotId={}, eventId={}, disposition={}",
            robotDeviceId, receipt.getEventId(), receipt.getDisposition());
    }
}
