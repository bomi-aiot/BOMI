package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.conversation.domain.ConversationOutcome;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for a conversation-ended robot event: sends the robot back to
 * its default position and finishes the scenario.
 *
 * <p>The voice/dialogue side (via the robot MQTT bridge) publishes this on the
 * robot {@code events} topic once the greeting conversation is over. The
 * scenario and conversation are identified by the v1 top-level correlation IDs.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class ConversationEndedHandler implements MqttMessageHandler {

    private static final String TYPE_CONVERSATION_ENDED = "CONVERSATION_ENDED";

    private final HomecomingOrchestrator orchestrator;

    public ConversationEndedHandler(HomecomingOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_EVENT
            && TYPE_CONVERSATION_ENDED.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        ConversationOutcome outcome = ConversationOutcome.valueOf(
            message.payload().path("outcome").asText());
        var reasonNode = message.payload().get("reasonCode");
        String reasonCode = reasonNode == null || reasonNode.isNull()
            ? null : reasonNode.asText();
        orchestrator.onConversationEnded(
            message.requireScenarioId(),
            message.requireConversationId(),
            message.sourceId(),
            outcome,
            reasonCode,
            message.occurredAt());
    }
}
