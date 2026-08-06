package com.ssafy.bomi.robot.application;

import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryAudit;
import com.ssafy.bomi.robot.domain.RobotModeRecoveryDisposition;
import com.ssafy.bomi.robot.repository.RobotModeRecoveryAuditRepository;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.robot.repository.RobotRepository.LockCandidate;
import com.ssafy.bomi.scenario.application.ScenarioStartGuard;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Recovers a stale database mode after an operator has separately confirmed physical safety.
 * This service deliberately has no MQTT publisher: it cannot stop motors or cancel movement.
 */
@Service
public class RobotModeRecoveryService {

    private final RobotRepository robotRepository;
    private final ScenarioRepository scenarioRepository;
    private final ScenarioStartGuard scenarioStartGuard;
    private final RobotModeRecoveryAuditRepository auditRepository;
    private final Clock clock;

    public RobotModeRecoveryService(
        RobotRepository robotRepository,
        ScenarioRepository scenarioRepository,
        ScenarioStartGuard scenarioStartGuard,
        RobotModeRecoveryAuditRepository auditRepository,
        Clock clock
    ) {
        this.robotRepository = robotRepository;
        this.scenarioRepository = scenarioRepository;
        this.scenarioStartGuard = scenarioStartGuard;
        this.auditRepository = auditRepository;
        this.clock = clock;
    }

    /**
     * Uses the same senior-row then Robot-row lock order as scenario admission. This makes the
     * final active-scenario check and the mode write atomic with a concurrent scenario start.
     */
    @Transactional
    public RobotModeRecoveryResult recoverToIdle(
        String deviceId,
        String operatorId,
        boolean physicalSafetyConfirmed,
        String reason
    ) {
        String normalizedDeviceId = requireText(deviceId, "deviceId", 64);
        String normalizedOperatorId = requireText(operatorId, "operatorId", 100);
        String normalizedReason = requireText(reason, "reason", 500);
        if (!physicalSafetyConfirmed) {
            throw new IllegalArgumentException("physicalSafetyConfirmed must be true");
        }

        LockCandidate candidate = robotRepository
            .findLockCandidateByDeviceId(normalizedDeviceId)
            .orElse(null);
        if (candidate == null) {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_UNKNOWN_ROBOT,
                null,
                normalizedDeviceId,
                null,
                "Robot is not registered");
        }
        if (candidate.getSeniorId() == null) {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_UNASSIGNED_ROBOT,
                candidate.getId(),
                normalizedDeviceId,
                null,
                "Robot has no senior assignment");
        }
        UUID expectedSeniorId = candidate.getSeniorId();

        if (!scenarioStartGuard.lockSenior(expectedSeniorId)) {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_SENIOR_NOT_FOUND,
                candidate.getId(),
                normalizedDeviceId,
                null,
                "Assigned senior does not exist");
        }

        Robot robot = robotRepository.findByIdForUpdate(candidate.getId()).orElse(null);
        if (robot == null || !Objects.equals(robot.getDeviceId(), normalizedDeviceId)) {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_UNKNOWN_ROBOT,
                candidate.getId(),
                normalizedDeviceId,
                null,
                "Robot registration changed while acquiring the lock");
        }
        if (!robot.isActive()) {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_INACTIVE_ROBOT,
                robot.getId(),
                robot.getDeviceId(),
                robot.getCurrentMode(),
                "Robot is inactive");
        }
        if (robot.getSeniorId() == null) {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_UNASSIGNED_ROBOT,
                robot.getId(),
                robot.getDeviceId(),
                robot.getCurrentMode(),
                "Robot has no senior assignment");
        }
        if (!Objects.equals(robot.getSeniorId(), expectedSeniorId)) {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_ASSIGNMENT_CHANGED,
                robot.getId(),
                robot.getDeviceId(),
                robot.getCurrentMode(),
                "Robot senior assignment changed while acquiring the lock");
        }

        boolean activeForSenior = scenarioRepository.existsBySeniorIdAndFinalStatusIn(
            expectedSeniorId, ScenarioStatus.activeStatuses());
        boolean activeForRobot = scenarioRepository.existsByRobotIdAndFinalStatusIn(
            robot.getId(), ScenarioStatus.activeStatuses());
        if (activeForSenior || activeForRobot) {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_ACTIVE_SCENARIO,
                robot.getId(),
                robot.getDeviceId(),
                robot.getCurrentMode(),
                "An active scenario exists");
        }

        RobotMode previousMode = robot.getCurrentMode();
        RobotModeRecoveryDisposition disposition;
        if (previousMode == RobotMode.IDLE) {
            disposition = RobotModeRecoveryDisposition.NO_OP_ALREADY_IDLE;
        } else if (previousMode == RobotMode.SAFE_STOP
            || previousMode == RobotMode.SCENARIO_ACTIVE) {
            robot.changeMode(RobotMode.IDLE);
            disposition = RobotModeRecoveryDisposition.RECOVERED;
        } else {
            return rejected(
                RobotModeRecoveryDisposition.REJECTED_MODE_NOT_RECOVERABLE,
                robot.getId(),
                robot.getDeviceId(),
                previousMode,
                "Only SAFE_STOP, stale SCENARIO_ACTIVE, or IDLE can be recovered");
        }

        OffsetDateTime recoveredAt = OffsetDateTime.now(clock);
        RobotModeRecoveryAudit audit = auditRepository.save(
            RobotModeRecoveryAudit.record(
                robot,
                normalizedOperatorId,
                previousMode,
                disposition,
                normalizedReason,
                recoveredAt));

        return new RobotModeRecoveryResult(
            disposition,
            robot.getId(),
            robot.getDeviceId(),
            previousMode,
            RobotMode.IDLE,
            audit.getId(),
            recoveredAt,
            disposition == RobotModeRecoveryDisposition.RECOVERED
                ? "Robot mode recovered to IDLE"
                : "Robot was already IDLE");
    }

    private static RobotModeRecoveryResult rejected(
        RobotModeRecoveryDisposition disposition,
        UUID robotId,
        String deviceId,
        RobotMode previousMode,
        String message
    ) {
        return new RobotModeRecoveryResult(
            disposition,
            robotId,
            deviceId,
            previousMode,
            previousMode,
            null,
            null,
            message);
    }

    private static String requireText(String value, String field, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        String normalized = value.trim();
        if (normalized.length() > maxLength) {
            throw new IllegalArgumentException(
                field + " must not exceed " + maxLength + " characters");
        }
        return normalized;
    }
}
