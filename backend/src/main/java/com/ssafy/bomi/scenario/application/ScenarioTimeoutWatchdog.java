package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.ScenarioTimeoutProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 너무 오래 활성 상태에 머문 시나리오를 강제로 끝내는 마지막 안전망이다.
 * AI 대화 전용 watchdog이 10초/5분 제한을 먼저 처리하지만, 그 작업 자체가 멈추거나
 * 예상하지 못한 활성 상태가 남았을 때 다음 시나리오가 영원히 막히지 않게 한다.
 *
 * <p>1분마다 깨어나 활성 상태로 {@code bomi.scenario-timeout.active-timeout}을 넘긴
 * 시나리오를 찾아 {@link Scenario#timeOut()} 처리한다. 정상 경로와 AI 대화 전용
 * watchdog은 항상 그보다 먼저 시나리오를 다음 상태로 옮긴다.</p>
 *
 * <p>{@link MedicationReminderScheduler}와 같은 폴링 방식을 쓴다: 예약 대신 매분
 * DB의 최신 상태를 다시 보므로 재시작·설정 변경마다 재조정이 필요 없다.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class ScenarioTimeoutWatchdog {

    private static final Logger log = LoggerFactory.getLogger(ScenarioTimeoutWatchdog.class);

    private final ScenarioRepository scenarioRepository;
    private final RobotRepository robotRepository;
    private final ScenarioTimeoutProperties properties;
    private final Clock clock;

    public ScenarioTimeoutWatchdog(
        ScenarioRepository scenarioRepository,
        RobotRepository robotRepository,
        ScenarioTimeoutProperties properties,
        Clock clock
    ) {
        this.scenarioRepository = scenarioRepository;
        this.robotRepository = robotRepository;
        this.properties = properties;
        this.clock = clock;
    }

    /** 1분 주기 틱. 예외가 새어 나가면 다음 틱이 조용히 죽으므로 전체를 감싼다. */
    @Scheduled(fixedDelay = 60_000)
    @Transactional
    public void tick() {
        try {
            OffsetDateTime cutoff = OffsetDateTime.now(clock).minus(properties.getActiveTimeout());
            List<Scenario> stale = scenarioRepository.findByFinalStatusInAndUpdatedAtBefore(
                ScenarioStatus.activeStatuses(), cutoff);
            for (Scenario scenario : stale) {
                expire(scenario);
            }
        } catch (RuntimeException ex) {
            log.error("Scenario timeout watchdog tick failed; will retry next tick", ex);
        }
    }

    private void expire(Scenario scenario) {
        if (scenario.isTerminated()) {
            // 조회와 처리 사이에 다른 경로(conv-end 등)가 이미 끝냈다. 건드리지 않는다.
            return;
        }
        scenario.timeOut();
        scenarioRepository.save(scenario);
        robotRepository.findById(scenario.getRobotId()).ifPresentOrElse(robot -> {
            robot.changeMode(RobotModePolicy.forScenario(scenario.getFinalStatus()));
            robotRepository.save(robot);
        }, () -> log.warn("Timed-out scenario references unknown robot; mode not synced: "
            + "scenarioId={}, robotId={}", scenario.getId(), scenario.getRobotId()));

        log.warn(
            "Scenario stuck past {} in an active state; forcing TIMED_OUT so the senior's next "
                + "scenario is not blocked: scenarioId={}, type={}, seniorId={}",
            properties.getActiveTimeout(), scenario.getId(), scenario.getScenarioType(),
            scenario.getSeniorId());
    }
}
