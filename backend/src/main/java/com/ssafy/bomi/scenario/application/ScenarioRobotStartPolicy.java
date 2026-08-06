package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Duration;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Component;

/**
 * Applies the Robot-side admission rules shared by every movement scenario.
 *
 * <p>The senior row is always locked before the Robot row. Operator mode recovery uses the same
 * order, so a recovery and a scenario start cannot commit an {@code IDLE + active scenario}
 * combination.</p>
 */
@Component
public class ScenarioRobotStartPolicy {

    public enum ModePolicy {
        /** Normal movement scenarios may start only from an idle Robot. */
        IDLE_ONLY(Set.of(RobotMode.IDLE)),
        /** Wake-word movement may approach while the independent rest guard remains active. */
        IDLE_OR_REST_GUARD(Set.of(RobotMode.IDLE, RobotMode.REST_GUARD));

        private final Set<RobotMode> allowedModes;

        ModePolicy(Set<RobotMode> allowedModes) {
            this.allowedModes = allowedModes;
        }

        boolean allows(RobotMode mode) {
            return allowedModes.contains(mode);
        }
    }

    public enum BlockReason {
        UNKNOWN_ROBOT,
        UNREGISTERED_ROBOT,
        INACTIVE_ROBOT,
        UNASSIGNED_ROBOT,
        ACTIVE_SCENARIO_EXISTS,
        COOLDOWN_ACTIVE,
        SAFE_STOP,
        REST_GUARD,
        BUSY_MODE
    }

    public record Decision(Robot robot, BlockReason blockReason) {

        public static Decision allowed(Robot robot) {
            return new Decision(Objects.requireNonNull(robot), null);
        }

        public static Decision blocked(BlockReason reason) {
            return new Decision(null, Objects.requireNonNull(reason));
        }

        public boolean allowed() {
            return blockReason == null;
        }
    }

    private final ScenarioStartGuard startGuard;
    private final RobotRepository robotRepository;
    private final ScenarioRepository scenarioRepository;

    public ScenarioRobotStartPolicy(
        ScenarioStartGuard startGuard,
        RobotRepository robotRepository,
        ScenarioRepository scenarioRepository
    ) {
        this.startGuard = startGuard;
        this.robotRepository = robotRepository;
        this.scenarioRepository = scenarioRepository;
    }

    /** Resolves and locks the Robot assigned to a known senior. */
    public Decision admitBySenior(
        UUID seniorId,
        ScenarioType type,
        Duration cooldown,
        ModePolicy modePolicy
    ) {
        var guardBlock = startGuard.check(seniorId, type, cooldown);
        if (guardBlock.isPresent()) {
            return Decision.blocked(mapGuardBlock(guardBlock.get()));
        }

        Robot robot = robotRepository.findBySeniorIdForUpdate(seniorId).orElse(null);
        return validateLockedRobot(robot, seniorId, modePolicy);
    }

    /** Resolves an MQTT device id, then locks senior and Robot rows in the shared order. */
    public Decision admitByDevice(
        String robotDeviceId,
        ScenarioType type,
        Duration cooldown,
        ModePolicy modePolicy
    ) {
        RobotRepository.LockCandidate candidate = robotRepository
            .findLockCandidateByDeviceId(robotDeviceId).orElse(null);
        if (candidate == null) {
            return Decision.blocked(BlockReason.UNKNOWN_ROBOT);
        }
        UUID admissionSeniorId = candidate.getSeniorId();
        if (admissionSeniorId == null) {
            return Decision.blocked(BlockReason.UNASSIGNED_ROBOT);
        }

        var guardBlock = startGuard.check(admissionSeniorId, type, cooldown);
        if (guardBlock.orElse(null) == ScenarioStartGuard.BlockReason.SENIOR_NOT_FOUND) {
            return Decision.blocked(BlockReason.UNASSIGNED_ROBOT);
        }

        Robot robot = robotRepository.findByDeviceIdForUpdate(robotDeviceId).orElse(null);
        Decision robotDecision = validateLockedRobot(robot, admissionSeniorId, modePolicy);
        if (!robotDecision.allowed()) {
            return robotDecision;
        }
        if (guardBlock.isPresent()) {
            return Decision.blocked(mapGuardBlock(guardBlock.get()));
        }
        return robotDecision;
    }

    private Decision validateLockedRobot(
        Robot robot,
        UUID expectedSeniorId,
        ModePolicy modePolicy
    ) {
        if (robot == null) {
            return Decision.blocked(BlockReason.UNKNOWN_ROBOT);
        }
        if (robot.getDeviceId() == null || robot.getDeviceId().isBlank()) {
            return Decision.blocked(BlockReason.UNREGISTERED_ROBOT);
        }
        if (!robot.isActive()) {
            return Decision.blocked(BlockReason.INACTIVE_ROBOT);
        }
        if (robot.getSeniorId() == null || !robot.getSeniorId().equals(expectedSeniorId)) {
            return Decision.blocked(BlockReason.UNASSIGNED_ROBOT);
        }
        if (robot.getCurrentMode() == RobotMode.SAFE_STOP) {
            return Decision.blocked(BlockReason.SAFE_STOP);
        }
        if (scenarioRepository.existsByRobotIdAndFinalStatusIn(
                robot.getId(), ScenarioStatus.activeStatuses())) {
            return Decision.blocked(BlockReason.ACTIVE_SCENARIO_EXISTS);
        }
        if (!modePolicy.allows(robot.getCurrentMode())) {
            return Decision.blocked(robot.getCurrentMode() == RobotMode.REST_GUARD
                ? BlockReason.REST_GUARD
                : BlockReason.BUSY_MODE);
        }
        return Decision.allowed(robot);
    }

    private static BlockReason mapGuardBlock(ScenarioStartGuard.BlockReason reason) {
        return switch (reason) {
            case SENIOR_NOT_FOUND -> BlockReason.UNASSIGNED_ROBOT;
            case ACTIVE_SCENARIO_EXISTS -> BlockReason.ACTIVE_SCENARIO_EXISTS;
            case COOLDOWN_ACTIVE -> BlockReason.COOLDOWN_ACTIVE;
        };
    }
}
