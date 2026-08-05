package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for a robot navigation result using MQTT contract v1.
 *
 * <p>During the Robot migration window, the legacy nested scenarioId/status form
 * is read only when no v1 correlation field is present. The parser rejects mixed
 * envelopes before this handler runs.</p>
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
        String outcome;
        String commandId = null;
        if (message.legacyContract()) {
            String status = message.payload().path("status").asText();
            log.warn("Reading legacy NAVIGATION_RESULT without commandId; remove after Robot "
                    + "v1 migration: scenarioId={}, robotId={}",
                message.requireScenarioId(), message.sourceId());
            outcome = switch (status) {
                case "ARRIVED" -> "SUCCEEDED";
                case "CANCELLED" -> "CANCELLED";
                default -> "FAILED";
            };
        } else {
            outcome = message.payload().path("outcome").asText();
            commandId = message.requireCommandId();
        }

        switch (outcome) {
            case "SUCCEEDED" -> orchestrator.onRobotArrived(
                message.requireScenarioId(), message.sourceId(), commandId,
                message.legacyContract());
            case "FAILED" -> orchestrator.onNavigationFailed(
                message.requireScenarioId(), message.sourceId(), commandId,
                message.legacyContract());
            case "CANCELLED" -> orchestrator.onNavigationCancelled(
                message.requireScenarioId(), message.sourceId(), commandId,
                message.legacyContract());
            case "TIMED_OUT" -> orchestrator.onNavigationTimedOut(
                message.requireScenarioId(), message.sourceId(), commandId,
                message.legacyContract());
            default -> log.warn("Unexpected validated navigation outcome: {}", outcome);
        }
    }
}
