package com.ssafy.bomi.occupancy.application;

import com.ssafy.bomi.occupancy.application.EntranceDirectionResolver.Signal;
import com.ssafy.bomi.occupancy.config.EntranceProperties;
import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import com.ssafy.bomi.occupancy.domain.OccupancyEvent;
import com.ssafy.bomi.occupancy.repository.OccupancyEventRepository;
import com.ssafy.bomi.robot.domain.OccupancyStatus;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Turns entrance sensor signals into a confirmed direction, occupancy and greeting
 * (S15P11E102-226).
 *
 * <p>This is the server half of the split agreed in 208:</p>
 *
 * <pre>
 *   Pi (two sensors) → Jetson → Backend
 *                      │         ├ direction (IN/OUT) from the signal order
 *                      │         ├ authoritative occupancy
 *                      │         └ whether the robot speaks, and what
 *                      └ timestamp normalization, conservative UNKNOWN, forwarding
 * </pre>
 *
 * <p><b>The robot deliberately cannot do this.</b> Without direction it can only say
 * UNKNOWN, which is honest but useless for greeting. Here we have the event history and
 * the facts a greeting depends on.</p>
 */
@Service
public class DoorEventService {

    private static final Logger log = LoggerFactory.getLogger(DoorEventService.class);

    private final EntranceDirectionResolver resolver;
    private final GreetingDecider greetingDecider;
    private final OccupancyEventRepository occupancyEventRepository;
    private final RobotRepository robotRepository;
    private final EntranceProperties properties;
    private final ObjectProvider<HomecomingOrchestrator> orchestratorProvider;

    /** 마지막으로 확정한 통과. 짧은 시간 안의 반대 방향을 모순으로 잡는 데 쓴다. */
    private final Map<UUID, Passage> lastPassage = new ConcurrentHashMap<>();

    public DoorEventService(EntranceDirectionResolver resolver,
        GreetingDecider greetingDecider,
        OccupancyEventRepository occupancyEventRepository,
        RobotRepository robotRepository,
        EntranceProperties properties,
        ObjectProvider<HomecomingOrchestrator> orchestratorProvider) {
        this.resolver = resolver;
        this.greetingDecider = greetingDecider;
        this.occupancyEventRepository = occupancyEventRepository;
        this.robotRepository = robotRepository;
        this.properties = properties;
        // ObjectProvider 인 이유: HomecomingOrchestrator 는 MQTT 가 켜진 경우에만
        // 빈으로 존재한다. 직접 주입하면 브로커 없는 환경에서 이 서비스까지 못 뜨고,
        // 그러면 재실 반영이라는 안전 경로가 인사 때문에 죽는다.
        this.orchestratorProvider = orchestratorProvider;
    }

    /**
     * Accepts one entrance signal.
     *
     * @param occurredAt the Jetson's normalized arrival time, not the Pi's clock
     * @param reportedAt what the Pi claimed, kept for the record so a broken RTC is visible
     * @return what the robot should do, if anything
     */
    @Transactional
    public DoorEventOutcome accept(UUID seniorId, Signal signal,
        OffsetDateTime occurredAt, OffsetDateTime reportedAt) {

        Optional<OccupancyDirection> resolved = resolver.observe(seniorId, signal, occurredAt);
        if (resolved.isEmpty()) {
            // 반쪽짜리 통과다. 짝이 오기를 기다린다. 문만 열리고 아무도 지나가지 않았다면
            // 짝은 오지 않고, 재실 상태는 건드리지 않은 채로 끝난다.
            return DoorEventOutcome.pending();
        }

        OccupancyDirection direction = resolved.get();
        if (contradictsRecent(seniorId, direction, occurredAt)) {
            return recordContradiction(seniorId, direction, occurredAt, reportedAt);
        }

        // awaySince 는 이번 통과로 덮어쓰기 '전에' 읽어야 한다. 귀가 인사에서
        // "오래 걸으셨네요"를 판단하는 근거가 직전 외출 시각이기 때문이다.
        OffsetDateTime awaySince = awaySince(seniorId);
        lastPassage.put(seniorId, new Passage(direction, occurredAt));

        OccupancyStatus status = direction == OccupancyDirection.IN
            ? OccupancyStatus.HOME
            : OccupancyStatus.AWAY;

        applyOccupancy(seniorId, status, occurredAt);
        occupancyEventRepository.save(OccupancyEvent.passage(
            seniorId, robotId(seniorId), direction, status, occurredAt, reportedAt));

        String greeting = greeting(seniorId, direction, awaySince, occurredAt).orElse(null);
        dispatch(seniorId, greeting);
        return new DoorEventOutcome(direction, status, greeting);
    }

    /**
     * Sends the greeting to the robot over the command channel.
     *
     * <p><b>Why MQTT and not the HTTP response.</b> The robot already has an ingress path
     * for backend-commanded speech ({@code backend_command}, built in 208), and it skips the
     * gate because the backend has already judged. Answering in the HTTP body would create a
     * second way for the robot to be told to speak, and two paths means two sets of rules
     * about when it may. The response still reports the decision so tests and logs can see
     * it — but the delivery is here.</p>
     *
     * <p>The orchestrator only exists when MQTT is enabled. With it off — every test run, and
     * any deploy without a broker — the decision is still made and recorded, just not spoken.
     * That is the honest degradation: occupancy is the safety signal and it lands either way.</p>
     */
    private void dispatch(UUID seniorId, String greeting) {
        if (greeting == null) {
            return;
        }
        HomecomingOrchestrator orchestrator = orchestratorProvider.getIfAvailable();
        if (orchestrator == null) {
            log.info("MQTT is disabled; the greeting for senior {} was decided but not spoken",
                seniorId);
            return;
        }
        try {
            orchestrator.startHomecoming(seniorId, null, greeting);
        } catch (RuntimeException error) {
            // 인사를 못 보낸 것이 재실 반영을 되돌릴 이유는 아니다. 재실은 안전
            // 신호이고 인사는 그렇지 않다 — 여기서 예외를 올리면 트랜잭션이 말려
            // occupancy_event 까지 사라진다.
            log.warn("could not dispatch the greeting for senior {}: {}",
                seniorId, error.toString());
        }
    }

    /**
     * A reversal too soon to believe.
     *
     * <p>A delivery produces exactly this: somebody walks to the door, it opens, and moments
     * later the pattern runs backwards. Believing both readings flips occupancy twice and
     * greets a senior who never went anywhere.</p>
     *
     * <p><b>We do not pick the more likely story.</b> On contradiction the answer is
     * {@code UNKNOWN}, and speech settles it — the robot promotes to {@code HOME} the moment
     * it hears them (CLAUDE.md §11).</p>
     */
    private boolean contradictsRecent(UUID seniorId, OccupancyDirection direction,
        OffsetDateTime at) {
        Passage previous = lastPassage.get(seniorId);
        if (previous == null || previous.direction() == direction) {
            return false;
        }
        Duration since = Duration.between(previous.at(), at);
        return !since.isNegative() && since.compareTo(properties.getReversalWindow()) < 0;
    }

    private DoorEventOutcome recordContradiction(UUID seniorId, OccupancyDirection direction,
        OffsetDateTime occurredAt, OffsetDateTime reportedAt) {

        log.info("entrance reversed within {} for senior {}; treating it as a contradiction "
            + "and falling back to UNKNOWN", properties.getReversalWindow(), seniorId);

        lastPassage.remove(seniorId);
        resolver.forget(seniorId);
        applyOccupancy(seniorId, OccupancyStatus.UNKNOWN, occurredAt);
        occupancyEventRepository.save(OccupancyEvent.passage(
            seniorId, robotId(seniorId), direction, OccupancyStatus.UNKNOWN,
            occurredAt, reportedAt));

        // 인사하지 않는다. 배달일 가능성이 크고, 아무 데도 안 가신 분께 "다녀오세요"는
        // 로봇이 상황을 못 읽고 있다는 신호다.
        return new DoorEventOutcome(direction, OccupancyStatus.UNKNOWN, null);
    }

    /**
     * The greeting, unless it is already too late to say it.
     *
     * <p>Ten minutes late is worse than silence — the robot announces to an empty hallway.
     * An expired greeting is <b>dropped, not rescheduled</b> (CLAUDE.md §11).</p>
     */
    private Optional<String> greeting(UUID seniorId, OccupancyDirection direction,
        OffsetDateTime awaySince, OffsetDateTime passageAt) {

        Duration age = Duration.between(passageAt, OffsetDateTime.now());
        if (age.compareTo(properties.getGreetingTtl()) > 0) {
            log.info("greeting for senior {} is {}s old; dropping it rather than announcing "
                + "to an empty hallway", seniorId, age.toSeconds());
            return Optional.empty();
        }
        return greetingDecider.decide(seniorId, direction, awaySince, passageAt);
    }

    /** 언제부터 나가 계셨는지. 귀가 인사에서 "오래 걸으셨네요"를 판단하는 근거다. */
    private OffsetDateTime awaySince(UUID seniorId) {
        Passage previous = lastPassage.get(seniorId);
        return previous != null && previous.direction() == OccupancyDirection.OUT
            ? previous.at()
            : null;
    }

    private void applyOccupancy(UUID seniorId, OccupancyStatus status, OffsetDateTime at) {
        robotRepository.findBySeniorId(seniorId).ifPresentOrElse(robot -> {
            robot.applyOccupancy(status, at);
            robotRepository.save(robot);
        }, () -> log.warn("no robot for senior {}; occupancy {} recorded as an event only",
            seniorId, status));
    }

    private UUID robotId(UUID seniorId) {
        return robotRepository.findBySeniorId(seniorId).map(Robot::getId).orElse(null);
    }

    /**
     * What the robot should do about one entrance signal.
     *
     * @param direction null while the passage is still incomplete
     * @param occupancy the confirmed value to push to the robot, or null when unchanged
     * @param greeting the single sentence to speak, or null to stay quiet
     */
    public record DoorEventOutcome(OccupancyDirection direction, OccupancyStatus occupancy,
        String greeting) {

        static DoorEventOutcome pending() {
            return new DoorEventOutcome(null, null, null);
        }

        /** True when this signal completed a passage. */
        public boolean resolved() {
            return direction != null;
        }
    }

    private record Passage(OccupancyDirection direction, OffsetDateTime at) {
    }
}
