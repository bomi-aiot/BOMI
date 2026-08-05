package com.ssafy.bomi.scenario.inbound;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.WalkOrchestrator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** The one inbound adapter for WALK FOLLOW_RESULT messages. */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class FollowResultHandler implements MqttMessageHandler {

    private final WalkOrchestrator orchestrator;

    public FollowResultHandler(WalkOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_RESULT
            && "FOLLOW_RESULT".equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        JsonNode payload = message.payload();
        JsonNode reason = payload.get("reasonCode");
        orchestrator.onFollowResult(
            message.eventId(),
            message.requireScenarioId(),
            message.sourceId(),
            message.requireCommandId(),
            message.occurredAt(),
            payload.path("outcome").asText(),
            payload.path("resultCode").asText(),
            reason == null || reason.isNull() ? null : reason.asText());
    }
}
