package com.ssafy.bomi.robot.application;

import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.OffsetDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OperatorRobotRuntimeQueryService {

    private final RobotRepository robotRepository;
    private final ScenarioRepository scenarioRepository;
    private final Clock clock;

    public OperatorRobotRuntimeQueryService(
        RobotRepository robotRepository,
        ScenarioRepository scenarioRepository,
        Clock clock
    ) {
        this.robotRepository = robotRepository;
        this.scenarioRepository = scenarioRepository;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public OperatorRobotRuntimeState get(String deviceId) {
        if (deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException("deviceId must not be blank");
        }
        Robot robot = robotRepository.findByDeviceId(deviceId.trim())
            .orElseThrow(() -> new OperatorRobotNotFoundException(deviceId.trim()));
        var scenarios = scenarioRepository
            .findByRobotIdAndFinalStatusInOrderByUpdatedAtDesc(
                robot.getId(), ScenarioStatus.activeStatuses())
            .stream()
            .map(scenario -> new OperatorRobotRuntimeState.ActiveScenario(
                scenario.getId(), scenario.getScenarioType(), scenario.getFinalStatus(),
                scenario.getActiveNavigationTarget(),
                scenario.getActiveNavigationCommandId(), scenario.getUpdatedAt()))
            .toList();
        return new OperatorRobotRuntimeState(
            robot.getId(), robot.getDeviceId(), robot.isActive(), robot.getSeniorId(),
            robot.getCurrentMode(), robot.getOccupancyStatus(), robot.getOccupancyObservedAt(),
            robot.getDoorNodeHeartbeatAt(), scenarios, OffsetDateTime.now(clock));
    }
}
