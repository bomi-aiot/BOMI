package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.WalkTimeoutProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** WALK-specific acknowledgement and maximum-duration safety watchdog. */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class WalkTimeoutWatchdog {

    private static final Logger log = LoggerFactory.getLogger(WalkTimeoutWatchdog.class);
    private static final String TIMEOUT_RESULT_CODE = "UNCHANGED";
    private static final String TIMEOUT_REASON_CODE = "EXECUTION_TIMEOUT";

    private final ScenarioRepository scenarioRepository;
    private final RobotRepository robotRepository;
    private final RobotCommandPublisher commandPublisher;
    private final WalkTimeoutProperties properties;
    private final Clock clock;

    public WalkTimeoutWatchdog(
        ScenarioRepository scenarioRepository,
        RobotRepository robotRepository,
        RobotCommandPublisher commandPublisher,
        WalkTimeoutProperties properties,
        Clock clock
    ) {
        this.scenarioRepository = scenarioRepository;
        this.robotRepository = robotRepository;
        this.commandPublisher = commandPublisher;
        this.properties = properties;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${bomi.walk.timeout-check-interval-millis:1000}")
    @Transactional
    public void tick() {
        try {
            OffsetDateTime now = OffsetDateTime.now(clock);
            for (Scenario scenario : scenarioRepository.findActiveWalksForUpdate(
                    ScenarioStatus.activeStatuses())) {
                if (timedOut(scenario, now)) {
                    timeOut(scenario, now);
                }
            }
        } catch (RuntimeException ex) {
            log.error("Walk timeout watchdog tick failed; will retry next tick", ex);
        }
    }

    private boolean timedOut(Scenario scenario, OffsetDateTime now) {
        boolean maximumDurationExpired = expired(
            scenario.getFollowStartRequestedAt(), properties.getMaxDuration(), now);
        if (maximumDurationExpired) {
            return true;
        }
        return switch (scenario.getFinalStatus()) {
            case STARTING_FOLLOW -> expired(
                scenario.getFollowStartRequestedAt(), properties.getFollowStartAckTimeout(), now);
            case FOLLOWING -> false;
            case STOPPING_FOLLOW -> scenario.getFollowingStartedAt() == null
                ? expired(
                    scenario.getFollowStartRequestedAt(),
                    properties.getFollowStartAckTimeout(),
                    now)
                : expired(
                    laterOf(
                        scenario.getFollowStopRequestedAt(), scenario.getFollowingStartedAt()),
                    properties.getFollowStopAckTimeout(),
                    now);
            default -> false;
        };
    }

    private void timeOut(Scenario scenario, OffsetDateTime now) {
        Robot robot = robotRepository.findByIdForUpdate(scenario.getRobotId()).orElse(null);
        String stopCommandId = scenario.getFollowStopCommandId();
        if (stopCommandId == null) {
            stopCommandId = UUID.randomUUID().toString();
            scenario.beginFollowStop(stopCommandId, now);
        }

        // Re-publishing an existing STOP uses the same commandId; Robot command idempotency
        // makes this a safe best-effort retry instead of creating another logical command.
        if (robot != null && robot.getDeviceId() != null) {
            commandPublisher.publish(new RobotCommand(
                stopCommandId,
                scenario.getId(),
                robot.getDeviceId(),
                RobotCommandType.FOLLOW_STOP,
                now,
                now.plus(properties.getFollowStopAckTimeout()),
                Map.of()));
        }

        String eventId = "timeout-" + scenario.getId();
        scenario.recordFollowResult(
            eventId, stopCommandId, TIMEOUT_RESULT_CODE, TIMEOUT_REASON_CODE, now);
        scenario.timeOut(TIMEOUT_RESULT_CODE, TIMEOUT_REASON_CODE);
        scenarioRepository.save(scenario);

        if (robot != null) {
            robot.changeMode(RobotMode.SAFE_STOP);
            robotRepository.save(robot);
        }
        log.warn("WALK timed out after best-effort FOLLOW_STOP: scenarioId={}, state={}, "
                + "stopCommandId={}",
            scenario.getId(), scenario.getFinalStatus(), stopCommandId);
    }

    private static boolean expired(
        OffsetDateTime since,
        Duration timeout,
        OffsetDateTime now
    ) {
        return since != null && !now.isBefore(since.plus(timeout));
    }

    private static OffsetDateTime laterOf(OffsetDateTime first, OffsetDateTime second) {
        if (first == null) {
            return second;
        }
        if (second == null) {
            return first;
        }
        return first.isAfter(second) ? first : second;
    }
}
