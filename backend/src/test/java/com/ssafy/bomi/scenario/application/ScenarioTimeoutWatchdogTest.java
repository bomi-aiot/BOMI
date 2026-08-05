package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.ScenarioTimeoutProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * ScenarioStartGuard가 타입 무관으로 활성 시나리오 하나만으로 그 어르신의 모든 새
 * 시나리오를 막는다는 전제 위에서, "대화 핸드오프 신호가 안 올 때" 워치독이 그 활성
 * 상태를 강제로 끝내는지를 검증한다. 시계를 고정해 실제로 20분을 기다리지 않는다.
 */
class ScenarioTimeoutWatchdogTest {

    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final ScenarioTimeoutProperties properties = new ScenarioTimeoutProperties();
    private final Clock fixedClock =
        Clock.fixed(Instant.parse("2026-08-04T03:00:00Z"), ZoneOffset.UTC);

    private final UUID seniorId = UUID.randomUUID();
    private final UUID robotId = UUID.randomUUID();

    private ScenarioTimeoutWatchdog watchdog() {
        return new ScenarioTimeoutWatchdog(
            scenarioRepository, robotRepository, properties, fixedClock);
    }

    private Scenario conversingScenario() {
        Scenario scenario = Scenario.create(seniorId, robotId, ScenarioType.HOMECOMING);
        scenario.beginMovingToEntrance();
        scenario.checkInteraction();
        scenario.beginConversation();
        ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
        return scenario;
    }

    @Test
    void forcesTimedOutAndSyncsRobotModeForStaleActiveScenario() {
        Scenario stuck = conversingScenario();
        when(scenarioRepository.findByFinalStatusInAndUpdatedAtBefore(anyCollection(), any()))
            .thenReturn(List.of(stuck));
        Robot robot = Robot.create(seniorId, "robot-01");
        ReflectionTestUtils.setField(robot, "id", robotId);
        when(robotRepository.findById(robotId)).thenReturn(Optional.of(robot));

        watchdog().tick();

        assertThat(stuck.getFinalStatus()).isEqualTo(ScenarioStatus.TIMED_OUT);
        verify(scenarioRepository).save(stuck);
        assertThat(robot.getCurrentMode()).isEqualTo(RobotMode.SAFE_STOP);
        verify(robotRepository).save(robot);
    }

    @Test
    void usesConfiguredCutoff() {
        properties.setActiveTimeout(java.time.Duration.ofMinutes(20));
        when(scenarioRepository.findByFinalStatusInAndUpdatedAtBefore(anyCollection(), any()))
            .thenReturn(List.of());

        watchdog().tick();

        ArgumentCaptor<OffsetDateTime> cutoffCaptor = ArgumentCaptor.forClass(OffsetDateTime.class);
        verify(scenarioRepository).findByFinalStatusInAndUpdatedAtBefore(anyCollection(), cutoffCaptor.capture());
        assertThat(cutoffCaptor.getValue())
            .isEqualTo(OffsetDateTime.now(fixedClock).minusMinutes(20));
    }

    @Test
    void skipsScenarioAlreadyResolvedBetweenQueryAndProcessing() {
        Scenario alreadyDone = conversingScenario();
        alreadyDone.decideReturn();
        alreadyDone.returnToDefault();
        alreadyDone.complete(); // resolved by the normal path just before the watchdog got to it
        when(scenarioRepository.findByFinalStatusInAndUpdatedAtBefore(anyCollection(), any()))
            .thenReturn(List.of(alreadyDone));

        watchdog().tick();

        verify(scenarioRepository, never()).save(any());
        verify(robotRepository, never()).save(any());
    }

    @Test
    void tickSwallowsRuntimeExceptionsSoNextTickCanRetry() {
        when(scenarioRepository.findByFinalStatusInAndUpdatedAtBefore(anyCollection(), any()))
            .thenThrow(new RuntimeException("db hiccup"));

        watchdog().tick(); // must not throw
    }
}
