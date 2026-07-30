package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.HomecomingContract;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for a robot navigation result: advances or fails the scenario
 * the result refers to, based on the robot's reported {@code status}.
 *
 * <p>The scenario is identified by the {@code scenarioId} the robot echoes back
 * (see {@link HomecomingContract#readScenarioId}). Only an explicit
 * {@code ARRIVED} advances the scenario; {@code FAILED} stops it; any absent or
 * unknown status is logged and ignored (so a malformed result never counts as
 * an arrival).</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class NavigationResultHandler implements MqttMessageHandler {

    private static final Logger log = LoggerFactory.getLogger(NavigationResultHandler.class);
    private static final String TYPE_NAVIGATION_RESULT = "NAVIGATION_RESULT";

    private final HomecomingOrchestrator orchestrator;

    public NavigationResultHandler(HomecomingOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_RESULT
            && TYPE_NAVIGATION_RESULT.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        UUID scenarioId = HomecomingContract.readScenarioId(message.body());
        String status = HomecomingContract.readResultStatus(message.body());

        if (HomecomingContract.RESULT_STATUS_ARRIVED.equals(status)) {
            orchestrator.onRobotArrived(scenarioId);
        } else if (HomecomingContract.RESULT_STATUS_FAILED.equals(status)) {
            orchestrator.onNavigationFailed(scenarioId);
        } else {
            log.warn(
                "NAVIGATION_RESULT with absent/unknown status; ignoring: scenarioId={}, status={}",
                scenarioId, status);
        }
    }
}
