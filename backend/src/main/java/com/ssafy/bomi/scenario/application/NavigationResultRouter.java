package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Routes one NAVIGATION_RESULT to exactly one scenario-type orchestrator. */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class NavigationResultRouter {

    private static final Logger log = LoggerFactory.getLogger(NavigationResultRouter.class);

    private final ScenarioRepository scenarioRepository;
    private final HomecomingOrchestrator homecomingOrchestrator;
    private final WakeWordCallOrchestrator wakeWordCallOrchestrator;

    public NavigationResultRouter(
        ScenarioRepository scenarioRepository,
        HomecomingOrchestrator homecomingOrchestrator,
        WakeWordCallOrchestrator wakeWordCallOrchestrator
    ) {
        this.scenarioRepository = scenarioRepository;
        this.homecomingOrchestrator = homecomingOrchestrator;
        this.wakeWordCallOrchestrator = wakeWordCallOrchestrator;
    }

    public void route(
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        boolean legacyContract,
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        Scenario scenario = scenarioRepository.findById(scenarioId).orElse(null);
        if (scenario == null) {
            log.warn("Navigation result references unknown scenario; ignoring: scenarioId={}",
                scenarioId);
            return;
        }
        if (scenario.getScenarioType() == ScenarioType.WAKE_WORD_CALL) {
            wakeWordCallOrchestrator.onNavigationResult(
                scenarioId, sourceRobotId, commandId, legacyContract,
                outcome, resultCode, reasonCode);
            return;
        }
        if (scenario.getScenarioType() == ScenarioType.HOMECOMING
            || scenario.getScenarioType() == ScenarioType.WELLNESS_CHECK
            || scenario.getScenarioType() == ScenarioType.MEDICATION_REMINDER) {
            routeConversationScenario(
                scenarioId, sourceRobotId, commandId, legacyContract, outcome);
            return;
        }
        log.warn("No navigation result route for scenario type {}; ignoring: scenarioId={}",
            scenario.getScenarioType(), scenarioId);
    }

    private void routeConversationScenario(
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        boolean legacyContract,
        String outcome
    ) {
        switch (outcome) {
            case "SUCCEEDED" -> homecomingOrchestrator.onRobotArrived(
                scenarioId, sourceRobotId, commandId, legacyContract);
            case "FAILED" -> homecomingOrchestrator.onNavigationFailed(
                scenarioId, sourceRobotId, commandId, legacyContract);
            case "CANCELLED" -> homecomingOrchestrator.onNavigationCancelled(
                scenarioId, sourceRobotId, commandId, legacyContract);
            case "TIMED_OUT" -> homecomingOrchestrator.onNavigationTimedOut(
                scenarioId, sourceRobotId, commandId, legacyContract);
            default -> log.warn("Unexpected validated navigation outcome: {}", outcome);
        }
    }
}
