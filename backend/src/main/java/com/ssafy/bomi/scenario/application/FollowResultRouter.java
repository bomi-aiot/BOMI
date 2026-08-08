package com.ssafy.bomi.scenario.application;

import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Routes one FOLLOW_RESULT to exactly one scenario-type orchestrator.
 *
 * <p>FOLLOW_START used to belong to the walk scenario alone, so the inbound
 * handler could pass every result straight to {@link WalkOrchestrator}. The
 * wake-word call now uses the same command to start the robot's turn-and-search
 * behaviour, so two scenarios share one result type and someone has to decide
 * which owner gets it. This mirrors {@link NavigationResultRouter}.</p>
 *
 * <p>Only WAKE_WORD_CALL is redirected. Everything else — including an unknown
 * or already-deleted scenario — keeps the previous path, so adding this router
 * cannot change how the walk scenario behaves. The lookup is a plain read; the
 * owning orchestrator takes its own row lock inside its own transaction.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class FollowResultRouter {

    private static final Logger log = LoggerFactory.getLogger(FollowResultRouter.class);

    private final ScenarioRepository scenarioRepository;
    private final WakeWordCallOrchestrator wakeWordCallOrchestrator;
    private final HomecomingOrchestrator homecomingOrchestrator;
    private final WalkOrchestrator walkOrchestrator;

    public FollowResultRouter(
        ScenarioRepository scenarioRepository,
        WakeWordCallOrchestrator wakeWordCallOrchestrator,
        HomecomingOrchestrator homecomingOrchestrator,
        WalkOrchestrator walkOrchestrator
    ) {
        this.scenarioRepository = scenarioRepository;
        this.wakeWordCallOrchestrator = wakeWordCallOrchestrator;
        this.homecomingOrchestrator = homecomingOrchestrator;
        this.walkOrchestrator = walkOrchestrator;
    }

    public void route(
        String eventId,
        UUID scenarioId,
        String sourceRobotId,
        String commandId,
        OffsetDateTime occurredAt,
        String outcome,
        String resultCode,
        String reasonCode
    ) {
        Scenario scenario = scenarioRepository.findById(scenarioId).orElse(null);
        if (scenario != null
            && scenario.getScenarioType() == ScenarioType.WAKE_WORD_CALL) {
            log.debug("Routing FOLLOW_RESULT to the wake-word call: scenarioId={}", scenarioId);
            wakeWordCallOrchestrator.onFollowResult(
                scenarioId, sourceRobotId, commandId, false,
                outcome, resultCode, reasonCode);
            return;
        }
        if (scenario != null && scenario.getScenarioType() == ScenarioType.HOMECOMING) {
            homecomingOrchestrator.onFollowResult(
                eventId, scenarioId, sourceRobotId, commandId, occurredAt,
                outcome, resultCode, reasonCode);
            return;
        }
        walkOrchestrator.onFollowResult(
            eventId, scenarioId, sourceRobotId, commandId, occurredAt,
            outcome, resultCode, reasonCode);
    }
}
