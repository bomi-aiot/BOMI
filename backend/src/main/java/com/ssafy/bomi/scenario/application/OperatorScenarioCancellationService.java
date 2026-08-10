package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.robot.repository.RobotRepository.LockCandidate;
import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationAudit;
import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationDisposition;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.repository.OperatorScenarioCancellationAuditRepository;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Safely terminates a stuck navigation scenario before normal mode recovery. */
@Service
public class OperatorScenarioCancellationService {

    private static final String REASON_CODE = "OPERATOR_CANCELLED";
    private final RobotRepository robotRepository;
    private final ScenarioRepository scenarioRepository;
    private final ScenarioStartGuard scenarioStartGuard;
    private final OperatorScenarioCancellationAuditRepository auditRepository;
    private final List<RobotCommandPublisher> commandPublishers;
    private final Clock clock;

    public OperatorScenarioCancellationService(
        RobotRepository robotRepository,
        ScenarioRepository scenarioRepository,
        ScenarioStartGuard scenarioStartGuard,
        OperatorScenarioCancellationAuditRepository auditRepository,
        List<RobotCommandPublisher> commandPublishers,
        Clock clock
    ) {
        this.robotRepository = robotRepository;
        this.scenarioRepository = scenarioRepository;
        this.scenarioStartGuard = scenarioStartGuard;
        this.auditRepository = auditRepository;
        this.commandPublishers = List.copyOf(commandPublishers);
        this.clock = clock;
    }

    @Transactional
    public OperatorScenarioCancellationResult cancelActiveNavigation(
        String deviceId, String operatorId, boolean physicalSafetyConfirmed, String reason
    ) {
        String normalizedDeviceId = text(deviceId, "deviceId", 64);
        String normalizedOperatorId = text(operatorId, "operatorId", 100);
        String normalizedReason = text(reason, "reason", 500);
        if (!physicalSafetyConfirmed) {
            throw new IllegalArgumentException("physicalSafetyConfirmed must be true");
        }

        LockCandidate candidate = robotRepository.findLockCandidateByDeviceId(normalizedDeviceId)
            .orElse(null);
        if (candidate == null) {
            return rejected(OperatorScenarioCancellationDisposition.REJECTED_UNKNOWN_ROBOT,
                null, normalizedDeviceId, null, "Robot is not registered");
        }
        if (candidate.getSeniorId() == null) {
            return rejected(OperatorScenarioCancellationDisposition.REJECTED_UNASSIGNED_ROBOT,
                candidate.getId(), normalizedDeviceId, null, "Robot has no senior assignment");
        }
        UUID expectedSeniorId = candidate.getSeniorId();
        if (!scenarioStartGuard.lockSenior(expectedSeniorId)) {
            return rejected(OperatorScenarioCancellationDisposition.REJECTED_SENIOR_NOT_FOUND,
                candidate.getId(), normalizedDeviceId, null, "Assigned senior does not exist");
        }

        Robot robot = robotRepository.findByIdForUpdate(candidate.getId()).orElse(null);
        if (robot == null || !Objects.equals(robot.getDeviceId(), normalizedDeviceId)) {
            return rejected(OperatorScenarioCancellationDisposition.REJECTED_UNKNOWN_ROBOT,
                candidate.getId(), normalizedDeviceId, null,
                "Robot registration changed while acquiring the lock");
        }
        if (!robot.isActive()) {
            return rejected(OperatorScenarioCancellationDisposition.REJECTED_INACTIVE_ROBOT,
                robot.getId(), robot.getDeviceId(), robot.getCurrentMode(), "Robot is inactive");
        }
        if (robot.getSeniorId() == null) {
            return rejected(OperatorScenarioCancellationDisposition.REJECTED_UNASSIGNED_ROBOT,
                robot.getId(), robot.getDeviceId(), robot.getCurrentMode(),
                "Robot has no senior assignment");
        }
        if (!Objects.equals(robot.getSeniorId(), expectedSeniorId)) {
            return rejected(OperatorScenarioCancellationDisposition.REJECTED_ASSIGNMENT_CHANGED,
                robot.getId(), robot.getDeviceId(), robot.getCurrentMode(),
                "Robot senior assignment changed while acquiring the lock");
        }

        List<Scenario> active = scenarioRepository.findActiveByRobotIdForUpdate(
            robot.getId(), ScenarioStatus.activeStatuses());
        if (active.isEmpty()) {
            return noOp(robot);
        }
        if (active.size() != 1) {
            return rejected(
                OperatorScenarioCancellationDisposition.REJECTED_MULTIPLE_ACTIVE_SCENARIOS,
                robot.getId(), robot.getDeviceId(), robot.getCurrentMode(),
                "Multiple active scenarios exist; manual investigation is required");
        }

        Scenario scenario = active.get(0);
        String targetCommandId = scenario.getActiveNavigationCommandId();
        boolean navigationCancellationRequired =
            targetCommandId != null && !targetCommandId.isBlank();
        if (navigationCancellationRequired && commandPublishers.size() != 1) {
            return rejected(
                OperatorScenarioCancellationDisposition.REJECTED_MQTT_UNAVAILABLE,
                robot.getId(), robot.getDeviceId(), robot.getCurrentMode(),
                "Exactly one MQTT Robot command publisher is required");
        }

        OffsetDateTime now = OffsetDateTime.now(clock);
        String cancelCommandId = navigationCancellationRequired
            ? UUID.randomUUID().toString()
            : null;
        ScenarioStatus previousStatus = scenario.getFinalStatus();
        RobotMode previousMode = robot.getCurrentMode();

        scenario.cancel("CANCELLED", REASON_CODE);
        robot.changeMode(RobotMode.SAFE_STOP);
        OperatorScenarioCancellationAudit audit = auditRepository.save(
            OperatorScenarioCancellationAudit.record(
                robot.getId(), robot.getDeviceId(), scenario.getId(), normalizedOperatorId,
                previousStatus, previousMode, targetCommandId, cancelCommandId,
                normalizedReason, now));

        if (navigationCancellationRequired) {
            commandPublishers.get(0).publish(new RobotCommand(
                cancelCommandId, scenario.getId(), robot.getDeviceId(), RobotCommandType.CANCEL,
                now, now.plusMinutes(2),
                Map.of("targetCommandId", targetCommandId, "reasonCode", REASON_CODE)));
        }

        return new OperatorScenarioCancellationResult(
            OperatorScenarioCancellationDisposition.CANCELLED,
            robot.getId(), robot.getDeviceId(), scenario.getId(), previousStatus,
            ScenarioStatus.CANCELLED, previousMode, RobotMode.SAFE_STOP,
            cancelCommandId, audit.getId(), now,
            navigationCancellationRequired
                ? "Scenario cancelled and navigation cancellation queued; recover SAFE_STOP "
                    + "to IDLE after verifying the robot stopped"
                : "Scenario cancelled; recover SAFE_STOP to IDLE after verifying the robot stopped");
    }

    private static OperatorScenarioCancellationResult noOp(Robot robot) {
        return new OperatorScenarioCancellationResult(
            OperatorScenarioCancellationDisposition.NO_OP_NO_ACTIVE_SCENARIO,
            robot.getId(), robot.getDeviceId(), null, null, null,
            robot.getCurrentMode(), robot.getCurrentMode(), null, null, null,
            "No active scenario exists");
    }

    private static OperatorScenarioCancellationResult rejected(
        OperatorScenarioCancellationDisposition disposition, UUID robotId,
        String deviceId, RobotMode mode, String message
    ) {
        return new OperatorScenarioCancellationResult(
            disposition, robotId, deviceId, null, null, null, mode, mode,
            null, null, null, message);
    }

    private static String text(String value, String field, int max) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        String normalized = value.trim();
        if (normalized.length() > max) {
            throw new IllegalArgumentException(field + " must not exceed " + max + " characters");
        }
        return normalized;
    }
}
