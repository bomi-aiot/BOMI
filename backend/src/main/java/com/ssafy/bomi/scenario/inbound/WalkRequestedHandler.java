package com.ssafy.bomi.scenario.inbound;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.WalkOrchestrator;
import com.ssafy.bomi.scenario.application.WalkRequest;
import com.ssafy.bomi.scenario.domain.WalkAction;
import com.ssafy.bomi.scenario.domain.WalkRequestIngress;
import com.ssafy.bomi.scenario.domain.WalkRequestSource;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Thin Voice MQTT adapter for the shared WALK application service. */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class WalkRequestedHandler implements MqttMessageHandler {

    private final WalkOrchestrator orchestrator;

    public WalkRequestedHandler(WalkOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_EVENT
            && "WALK_REQUESTED".equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        JsonNode payload = message.payload();
        orchestrator.handleRequest(new WalkRequest(
            WalkRequestIngress.MQTT,
            message.eventId(),
            message.sourceId(),
            WalkAction.valueOf(payload.path("action").asText()),
            WalkRequestSource.valueOf(payload.path("source").asText()),
            message.conversationId(),
            message.occurredAt()));
    }
}
