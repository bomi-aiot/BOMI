package com.ssafy.bomi.robot.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.robot.domain.OccupancyStatus;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.domain.RobotMode;
import com.ssafy.bomi.robot.repository.RobotRepository;
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
import org.springframework.test.util.ReflectionTestUtils;

class OperatorRobotRuntimeQueryServiceTest {

    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final OperatorRobotRuntimeQueryService service = new OperatorRobotRuntimeQueryService(
        robotRepository, scenarioRepository,
        Clock.fixed(Instant.parse("2026-08-08T01:00:00Z"), ZoneOffset.UTC));

    @Test
    void returnsRobotAndActiveNavigationSnapshot() {
        UUID robotId = UUID.randomUUID();
        Robot robot = Robot.create(UUID.randomUUID(), "bomi-AA001");
        ReflectionTestUtils.setField(robot, "id", robotId);
        robot.changeMode(RobotMode.SCENARIO_ACTIVE);
        robot.applyOccupancy(OccupancyStatus.HOME,
            OffsetDateTime.parse("2026-08-08T00:55:00Z"));

        Scenario scenario = Scenario.create(
            robot.getSeniorId(), robotId, ScenarioType.HOMECOMING);
        ReflectionTestUtils.setField(scenario, "id", UUID.randomUUID());
        ReflectionTestUtils.setField(scenario, "updatedAt",
            OffsetDateTime.parse("2026-08-08T00:59:00Z"));
        scenario.beginMovingToEntrance();
        scenario.expectNavigationResult("navigate-01", "ENTRANCE");

        when(robotRepository.findByDeviceId("bomi-AA001")).thenReturn(Optional.of(robot));
        when(scenarioRepository.findByRobotIdAndFinalStatusInOrderByUpdatedAtDesc(
            robotId, ScenarioStatus.activeStatuses())).thenReturn(List.of(scenario));

        OperatorRobotRuntimeState result = service.get("bomi-AA001");

        assertThat(result.currentMode()).isEqualTo(RobotMode.SCENARIO_ACTIVE);
        assertThat(result.occupancyStatus()).isEqualTo(OccupancyStatus.HOME);
        assertThat(result.activeScenarios()).singleElement().satisfies(active -> {
            assertThat(active.scenarioType()).isEqualTo(ScenarioType.HOMECOMING);
            assertThat(active.status()).isEqualTo(ScenarioStatus.MOVING_TO_ENTRANCE);
            assertThat(active.navigationTarget()).isEqualTo("ENTRANCE");
            assertThat(active.navigationCommandId()).isEqualTo("navigate-01");
        });
    }

    @Test
    void unknownRobotIsNotFound() {
        when(robotRepository.findByDeviceId("unknown")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.get("unknown"))
            .isInstanceOf(OperatorRobotNotFoundException.class);
    }
}
