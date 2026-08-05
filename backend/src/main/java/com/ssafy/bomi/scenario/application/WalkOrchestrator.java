package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.mqtt.inbound.MqttContractViolationException;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.WalkTimeoutProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.domain.WalkAction;
import com.ssafy.bomi.scenario.domain.WalkRequestDisposition;
import com.ssafy.bomi.scenario.domain.WalkRequestIngress;
import com.ssafy.bomi.scenario.domain.WalkRequestReceipt;
import com.ssafy.bomi.scenario.domain.WalkRequestSource;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.scenario.repository.WalkRequestReceiptRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Single application boundary shared by Voice MQTT and Guardian REST walk requests. */
@Service
public class WalkOrchestrator {

    private static final Logger log = LoggerFactory.getLogger(WalkOrchestrator.class);

    private final ScenarioRepository scenarioRepository;
    private final WalkRequestReceiptRepository receiptRepository;
    private final RobotRepository robotRepository;
    private final List<RobotCommandPublisher> commandPublishers;
    private final ScenarioStartGuard startGuard;
    private final WalkTimeoutProperties properties;
    private final Clock clock;

    public WalkOrchestrator(
        ScenarioRepository scenarioRepository,
        WalkRequestReceiptRepository receiptRepository,
        RobotRepository robotRepository,
        List<RobotCommandPublisher> commandPublishers,
        ScenarioStartGuard startGuard,
        WalkTimeoutProperties properties,
        Clock clock
    ) {
        this.scenarioRepository = scenarioRepository;
        this.receiptRepository = receiptRepository;
        this.robotRepository = robotRepository;
        this.commandPublishers = List.copyOf(commandPublishers);
        this.startGuard = startGuard;
        this.properties = properties;
        this.clock = clock;
    }

    /** Handles both MQTT and REST START/STOP without transport-specific policy branches. */
    @Transactional
    public WalkRequestResult handleRequest(WalkRequest request) {
        WalkRequestReceipt previous = findReceipt(request);
        if (previous != null) {
            return duplicateResult(previous, request);
        }
        return request.action() == WalkAction.START
            ? start(request)
            : stop(request);
    }

    /** Guardian adapter entrypoint; source and server occurrence time cannot be client-forged. */
    @Transactional
    public WalkRequestResult handleGuardianRequest(
        String requestId,
        String robotDeviceId,
        WalkAction action
    ) {
        return handleRequest(new WalkRequest(
            WalkRequestIngress.GUARDIAN_REST,
            requestId,
            robotDeviceId,
            action,
            WalkRequestSource.APP,
            null,
            OffsetDateTime.now(clock)));
    }

    private WalkRequestResult start(WalkRequest request) {
        Robot observedRobot = robotRepository.findByDeviceId(request.robotDeviceId()).orElse(null);
        if (observedRobot == null) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_UNKNOWN_ROBOT);
        }
        UUID admissionSeniorId = observedRobot.getSeniorId();
        if (admissionSeniorId == null) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_UNASSIGNED_ROBOT);
        }

        var blocked = startGuard.check(admissionSeniorId, ScenarioType.WALK, Duration.ZERO);
        WalkRequestReceipt previous = findReceipt(request);
        if (previous != null) {
            return duplicateResult(previous, request);
        }

        Robot robot = robotRepository.findByDeviceIdForUpdate(request.robotDeviceId()).orElse(null);
        if (robot == null) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_UNKNOWN_ROBOT);
        }
        if (!robot.isActive()) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_INACTIVE_ROBOT);
        }
        if (robot.getSeniorId() == null || !robot.getSeniorId().equals(admissionSeniorId)
            || blocked.orElse(null) == ScenarioStartGuard.BlockReason.SENIOR_NOT_FOUND) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_UNASSIGNED_ROBOT);
        }
        if (robot.getCurrentMode() == RobotMode.SAFE_STOP) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_SAFE_STOP);
        }
        if (robot.getCurrentMode() == RobotMode.REST_GUARD) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_REST_GUARD);
        }
        if (blocked.isPresent()) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_ACTIVE_SCENARIO);
        }
        if (robot.getCurrentMode() != RobotMode.IDLE) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_BUSY_MODE);
        }

        RobotCommandPublisher publisher = commandPublisherOrNull();
        if (publisher == null) {
            return transientResult(request, WalkRequestDisposition.REJECTED_MQTT_UNAVAILABLE);
        }

        ReceiptClaim requestClaim = claim(request);
        if (!requestClaim.created()) {
            return duplicateResult(requestClaim.receipt(), request);
        }

        OffsetDateTime now = OffsetDateTime.now(clock);
        String commandId = UUID.randomUUID().toString();
        Scenario scenario = Scenario.create(
            admissionSeniorId, robot.getId(), ScenarioType.WALK, request.requestId());
        scenario.recordTriggerContext(triggerContext(request));
        scenario.beginFollowStart(commandId, now);
        scenarioRepository.saveAndFlush(scenario);

        WalkRequestReceipt receipt = requestClaim.receipt();
        receipt.resolve(
            WalkRequestDisposition.ACCEPTED, scenario.getId(), scenario.getFinalStatus());

        robot.changeMode(RobotMode.SCENARIO_ACTIVE);
        robotRepository.save(robot);
        publishFollow(
            publisher, scenario, robot, commandId, RobotCommandType.FOLLOW_START,
            now, properties.getFollowStartAckTimeout());

        log.info("Walk START accepted: scenarioId={}, robotId={}, requestId={}, source={}",
            scenario.getId(), request.robotDeviceId(), request.requestId(), request.source());
        return result(receipt, false);
    }

    private WalkRequestResult stop(WalkRequest request) {
        Robot observedRobot = robotRepository.findByDeviceId(request.robotDeviceId()).orElse(null);
        if (observedRobot == null) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_UNKNOWN_ROBOT);
        }

        // Do not load the Scenario before taking the senior mutex. A preloaded entity can remain
        // stale in the persistence context even when the later repository call requests a
        // pessimistic lock, allowing two concurrent STOPs to overwrite each other's commandId.
        UUID seniorMutexId = observedRobot.getSeniorId();
        if (seniorMutexId != null) {
            startGuard.lockSenior(seniorMutexId);
        }

        WalkRequestReceipt previous = findReceipt(request);
        if (previous != null) {
            return duplicateResult(previous, request);
        }

        Scenario scenario = scenarioRepository.findActiveWalkByRobotIdForUpdate(
            observedRobot.getId(), ScenarioStatus.activeStatuses()).orElse(null);
        if (scenario == null) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_NO_ACTIVE_WALK);
        }
        Robot robot = robotRepository.findByIdForUpdate(scenario.getRobotId()).orElse(null);
        if (robot == null || !Objects.equals(robot.getDeviceId(), request.robotDeviceId())) {
            return rejectNew(request, WalkRequestDisposition.REJECTED_UNKNOWN_ROBOT);
        }
        if (scenario.getFinalStatus() == ScenarioStatus.STOPPING_FOLLOW) {
            ReceiptClaim requestClaim = claim(request);
            if (!requestClaim.created()) {
                return duplicateResult(requestClaim.receipt(), request);
            }
            WalkRequestReceipt receipt = requestClaim.receipt();
            receipt.resolve(WalkRequestDisposition.NO_OP_ALREADY_STOPPING,
                scenario.getId(), scenario.getFinalStatus());
            return result(receipt, false);
        }
        if (scenario.getFinalStatus() != ScenarioStatus.STARTING_FOLLOW
            && scenario.getFinalStatus() != ScenarioStatus.FOLLOWING) {
            throw new IllegalStateException(
                "Active WALK is in an unsupported STOP state: " + scenario.getFinalStatus());
        }

        RobotCommandPublisher publisher = commandPublisherOrNull();
        if (publisher == null) {
            return transientResult(request, WalkRequestDisposition.REJECTED_MQTT_UNAVAILABLE);
        }
        ReceiptClaim requestClaim = claim(request);
        if (!requestClaim.created()) {
            return duplicateResult(requestClaim.receipt(), request);
        }
        OffsetDateTime now = OffsetDateTime.now(clock);
        String commandId = UUID.randomUUID().toString();
        boolean waitForStartAck = scenario.getFinalStatus() == ScenarioStatus.STARTING_FOLLOW;
        scenario.beginFollowStop(commandId, now);
        scenarioRepository.saveAndFlush(scenario);

        WalkRequestReceipt receipt = requestClaim.receipt();
        receipt.resolve(
            WalkRequestDisposition.ACCEPTED, scenario.getId(), scenario.getFinalStatus());
        if (!waitForStartAck) {
            publishFollow(
                publisher, scenario, robot, commandId, RobotCommandType.FOLLOW_STOP,
                now, properties.getFollowStopAckTimeout());
        }

        log.info("Walk STOP accepted: scenarioId={}, robotId={}, requestId={}, deferred={}",
            scenario.getId(), request.robotDeviceId(), request.requestId(), waitForStartAck);
        return result(receipt, false);
    }

    /** Applies one correlated v1 FOLLOW_RESULT. */
    @Transactional
    public void onFollowResult(
        String eventId,
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        OffsetDateTime occurredAt,
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        Scenario scenario = scenarioRepository.findByIdForUpdate(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("FOLLOW_RESULT references unknown scenario; ignoring: scenarioId={}", scenarioId);
            return;
        }
        if (scenario.getScenarioType() != ScenarioType.WALK) {
            throw new MqttContractViolationException(
                "FOLLOW_RESULT scenario is not WALK: " + scenarioId);
        }

        Robot robot = robotRepository.findByIdForUpdate(scenario.getRobotId())
            .orElseThrow(() -> new IllegalStateException(
                "WALK scenario references unknown robot: " + scenario.getRobotId()));
        if (!Objects.equals(robot.getDeviceId(), sourceRobotId)) {
            throw new MqttContractViolationException(
                "FOLLOW_RESULT robotId does not match WALK scenario robot");
        }
        validateResult(outcome, resultCode, reasonCode);

        boolean startCommand = Objects.equals(commandId, scenario.getFollowStartCommandId());
        boolean stopCommand = Objects.equals(commandId, scenario.getFollowStopCommandId());
        if (!startCommand && !stopCommand) {
            throw new MqttContractViolationException(
                "FOLLOW_RESULT commandId does not match WALK START/STOP command");
        }
        if (scenario.isTerminated()) {
            log.info("Late correlated FOLLOW_RESULT ignored: scenarioId={}, status={}, commandId={}",
                scenarioId, scenario.getFinalStatus(), commandId);
            return;
        }

        boolean publishDeferredStop = false;
        if (startCommand) {
            publishDeferredStop = applyStartResult(
                scenario, eventId, commandId, occurredAt, outcome, resultCode, reasonCode);
        } else {
            applyStopResult(
                scenario, eventId, commandId, occurredAt, outcome, resultCode, reasonCode);
        }
        scenarioRepository.save(scenario);
        if (publishDeferredStop) {
            RobotCommandPublisher publisher = commandPublisherOrNull();
            if (publisher == null) {
                throw new IllegalStateException(
                    "FOLLOW_STOP publisher is unavailable after deferred START acknowledgement");
            }
            OffsetDateTime now = OffsetDateTime.now(clock);
            publishFollow(
                publisher, scenario, robot, scenario.getFollowStopCommandId(),
                RobotCommandType.FOLLOW_STOP, now, properties.getFollowStopAckTimeout());
        }
        if (scenario.isTerminated()) {
            RobotMode previousMode = robot.getCurrentMode();
            syncTerminalRobotMode(robot, scenario.getFinalStatus());
            if (robot.getCurrentMode() != previousMode) {
                robotRepository.save(robot);
            }
        }
    }

    private boolean applyStartResult(
        Scenario scenario,
        String eventId,
        String commandId,
        OffsetDateTime occurredAt,
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        ScenarioStatus status = scenario.getFinalStatus();
        if ("SUCCEEDED".equals(outcome)
            && ("STARTED".equals(resultCode) || "UNCHANGED".equals(resultCode))) {
            if (status == ScenarioStatus.STARTING_FOLLOW) {
                scenario.confirmFollowing(
                    eventId, commandId, resultCode, reasonCode, occurredAt,
                    OffsetDateTime.now(clock));
                return false;
            }
            if (status == ScenarioStatus.STOPPING_FOLLOW) {
                if (scenario.getFollowingStartedAt() == null) {
                    scenario.confirmFollowStartWhileStopping(
                        eventId, commandId, resultCode, reasonCode, occurredAt,
                        OffsetDateTime.now(clock));
                    return true;
                }
                return false;
            }
            if (status != ScenarioStatus.FOLLOWING) {
                throw new MqttContractViolationException(
                    "FOLLOW_START result is invalid in WALK status " + status);
            }
            return false;
        }

        if ("SUCCEEDED".equals(outcome) && !"STOPPED".equals(resultCode)) {
            throw new MqttContractViolationException(
                "Successful FOLLOW_START result must be STARTED, STOPPED, or UNCHANGED");
        }
        finishFromResult(
            scenario, eventId, commandId, occurredAt, outcome, resultCode, reasonCode);
        return false;
    }

    private void applyStopResult(
        Scenario scenario,
        String eventId,
        String commandId,
        OffsetDateTime occurredAt,
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        if (scenario.getFinalStatus() != ScenarioStatus.STOPPING_FOLLOW) {
            throw new MqttContractViolationException(
                "FOLLOW_STOP result is invalid in WALK status " + scenario.getFinalStatus());
        }
        if ("SUCCEEDED".equals(outcome)
            && !"STOPPED".equals(resultCode)
            && !"UNCHANGED".equals(resultCode)) {
            throw new MqttContractViolationException(
                "Successful FOLLOW_STOP result must be STOPPED or UNCHANGED");
        }
        finishFromResult(
            scenario, eventId, commandId, occurredAt, outcome, resultCode, reasonCode);
    }

    private static void finishFromResult(
        Scenario scenario,
        String eventId,
        String commandId,
        OffsetDateTime occurredAt,
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        scenario.recordFollowResult(
            eventId, commandId, resultCode, reasonCode, occurredAt);
        switch (outcome) {
            case "SUCCEEDED" -> scenario.complete(resultCode, reasonCode);
            case "FAILED" -> scenario.fail(resultCode, reasonCode);
            case "CANCELLED" -> scenario.cancel(resultCode, reasonCode);
            case "TIMED_OUT" -> scenario.timeOut(resultCode, reasonCode);
            default -> throw new MqttContractViolationException(
                "Unsupported FOLLOW_RESULT outcome '" + outcome + "'");
        }
    }

    private static void validateResult(String outcome, String resultCode, String reasonCode) {
        if (outcome == null
            || !List.of("SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT").contains(outcome)) {
            throw new MqttContractViolationException(
                "Unsupported FOLLOW_RESULT outcome '" + outcome + "'");
        }
        if (resultCode == null
            || !List.of("STARTED", "STOPPED", "UNCHANGED").contains(resultCode)) {
            throw new MqttContractViolationException(
                "Unsupported FOLLOW_RESULT resultCode '" + resultCode + "'");
        }
        if ("SUCCEEDED".equals(outcome) && reasonCode != null) {
            throw new MqttContractViolationException(
                "Successful FOLLOW_RESULT requires reasonCode=null");
        }
        if (!"SUCCEEDED".equals(outcome)
            && (reasonCode == null || reasonCode.isBlank())) {
            throw new MqttContractViolationException(
                "Unsuccessful FOLLOW_RESULT requires a reasonCode");
        }
    }

    private static void syncTerminalRobotMode(Robot robot, ScenarioStatus status) {
        if (status == ScenarioStatus.COMPLETED) {
            if (robot.getCurrentMode() == RobotMode.SCENARIO_ACTIVE) {
                robot.changeMode(RobotMode.IDLE);
            }
        } else {
            robot.changeMode(RobotMode.SAFE_STOP);
        }
    }

    private WalkRequestReceipt findReceipt(WalkRequest request) {
        return receiptRepository.findByIngressAndRequestId(
            request.ingress(), request.requestId()).orElse(null);
    }

    private WalkRequestResult duplicateResult(
        WalkRequestReceipt receipt,
        WalkRequest request
    ) {
        if (!receipt.describes(
                request.robotDeviceId(), request.action(), request.source(),
                request.conversationId(), request.occurredAt())) {
            return transientResult(request, WalkRequestDisposition.REJECTED_REQUEST_ID_REUSED);
        }
        return result(receipt, true);
    }

    private WalkRequestResult rejectNew(
        WalkRequest request,
        WalkRequestDisposition disposition
    ) {
        ReceiptClaim requestClaim = claim(request);
        if (!requestClaim.created()) {
            return duplicateResult(requestClaim.receipt(), request);
        }
        WalkRequestReceipt receipt = requestClaim.receipt();
        receipt.resolve(disposition, null, null);
        return result(receipt, false);
    }

    private ReceiptClaim claim(WalkRequest request) {
        int inserted = receiptRepository.insertIfAbsent(
            UUID.randomUUID(), request.ingress().name(), request.requestId(),
            request.robotDeviceId(), request.action().name(), request.source().name(),
            request.conversationId(), request.occurredAt());
        WalkRequestReceipt receipt = findReceipt(request);
        if (receipt == null) {
            throw new IllegalStateException("Walk request receipt claim was not observable");
        }
        return new ReceiptClaim(receipt, inserted == 1);
    }

    private record ReceiptClaim(WalkRequestReceipt receipt, boolean created) {}

    private static WalkRequestResult result(WalkRequestReceipt receipt, boolean duplicate) {
        return new WalkRequestResult(
            receipt.getRequestId(), receipt.getAction(), receipt.getDisposition().isAccepted(),
            receipt.getScenarioId(), receipt.getScenarioStatus(),
            receipt.getDisposition().reasonCode(), duplicate, receipt.getDisposition());
    }

    private static WalkRequestResult transientResult(
        WalkRequest request,
        WalkRequestDisposition disposition
    ) {
        return new WalkRequestResult(
            request.requestId(), request.action(), false, null, null,
            disposition.reasonCode(), false, disposition);
    }

    private RobotCommandPublisher commandPublisherOrNull() {
        return commandPublishers.size() == 1 ? commandPublishers.get(0) : null;
    }

    private static Map<String, Object> triggerContext(WalkRequest request) {
        Map<String, Object> context = new LinkedHashMap<>();
        context.put("ingress", request.ingress().name());
        context.put("source", request.source().name());
        context.put("occurredAt", request.occurredAt().toString());
        if (request.conversationId() != null) {
            context.put("conversationId", request.conversationId().toString());
        }
        return context;
    }

    private static void publishFollow(
        RobotCommandPublisher publisher,
        Scenario scenario,
        Robot robot,
        String commandId,
        RobotCommandType type,
        OffsetDateTime occurredAt,
        Duration ttl
    ) {
        publisher.publish(new RobotCommand(
            commandId,
            scenario.getId(),
            robot.getDeviceId(),
            type,
            occurredAt,
            occurredAt.plus(ttl),
            Map.of()));
    }
}
