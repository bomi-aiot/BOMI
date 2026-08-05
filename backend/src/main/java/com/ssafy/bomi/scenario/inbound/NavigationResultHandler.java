package com.ssafy.bomi.scenario.inbound;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.NavigationResultRouter;
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

    private final NavigationResultRouter router;

    public NavigationResultHandler(NavigationResultRouter router) {
        this.router = router;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_RESULT
            && TYPE_NAVIGATION_RESULT.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        String outcome;
        String resultCode;
        String reasonCode;
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
            resultCode = "ARRIVED".equals(status) ? "ARRIVED" : "NOT_ARRIVED";
            reasonCode = null;
        } else {
            outcome = message.payload().path("outcome").asText();
            resultCode = message.payload().path("resultCode").asText();
            JsonNode reasonNode = message.payload().get("reasonCode");
            reasonCode = reasonNode == null || reasonNode.isNull()
                ? null : reasonNode.asText();
            commandId = message.requireCommandId();
        }
        router.route(
            message.requireScenarioId(),
            message.sourceId(),
            commandId,
            message.legacyContract(),
            outcome,
            resultCode,
            reasonCode);
    }
}
