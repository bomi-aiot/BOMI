package com.ssafy.bomi.scenario.inbound;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.WakeWordCallOrchestrator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Thin MQTT adapter for AI-confirmed wake-word events. */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class WakeWordDetectedHandler implements MqttMessageHandler {

    private static final String TYPE = "WAKE_WORD_DETECTED";

    private final WakeWordCallOrchestrator orchestrator;

    public WakeWordDetectedHandler(WakeWordCallOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_EVENT
            && TYPE.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        JsonNode payload = message.payload();
        JsonNode confidenceNode = payload.get("confidence");
        Double confidence = confidenceNode == null ? null : confidenceNode.doubleValue();
        orchestrator.onWakeWordDetected(
            message.sourceId(),
            message.eventId(),
            message.occurredAt(),
            payload.path("keyword").asText(),
            confidence);
    }
}
