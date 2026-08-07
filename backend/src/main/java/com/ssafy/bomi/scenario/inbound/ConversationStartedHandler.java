package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/** Correlates AI's start acknowledgement with the stored scenario conversation. */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class ConversationStartedHandler implements MqttMessageHandler {

    private static final String TYPE = "CONVERSATION_STARTED";

    private final HomecomingOrchestrator orchestrator;

    public ConversationStartedHandler(HomecomingOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_EVENT
            && TYPE.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        ConversationIntent intent = ConversationIntent.valueOf(
            message.payload().path("intent").asText());
        orchestrator.onConversationStarted(
            message.requireScenarioId(),
            message.requireConversationId(),
            message.requireCommandId(),
            message.sourceId(),
            intent,
            message.occurredAt());
    }
}
