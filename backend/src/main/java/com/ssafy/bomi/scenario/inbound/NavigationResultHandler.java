package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.HomecomingContract;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import java.util.UUID;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for a robot navigation result: advances the scenario the
 * result refers to.
 *
 * <p>The scenario is identified by the {@code scenarioId} the robot echoes back
 * in the result payload (see {@link HomecomingContract#readScenarioId}).</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class NavigationResultHandler implements MqttMessageHandler {

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
        orchestrator.onRobotArrived(scenarioId);
    }
}
