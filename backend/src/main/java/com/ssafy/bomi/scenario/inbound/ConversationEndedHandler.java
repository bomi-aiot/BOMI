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
 * Inbound adapter for a conversation-ended robot event: sends the robot back to
 * its default position and finishes the scenario.
 *
 * <p>The voice/dialogue side (via the robot MQTT bridge) publishes this on the
 * robot {@code events} topic once the greeting conversation is over. The
 * scenario is identified by the {@code scenarioId} echoed in the payload (see
 * {@link HomecomingContract#readScenarioId}). This is the seam that replaces the
 * MVP logging stub so the homecoming happy path can complete end to end.</p>
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
        UUID scenarioId = HomecomingContract.readScenarioId(message.body());
        orchestrator.onConversationEnded(scenarioId);
    }
}
