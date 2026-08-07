package com.ssafy.bomi.scenario.inbound;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.FollowResultRouter;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * The one inbound adapter for FOLLOW_RESULT messages.
 *
 * <p>Two scenarios now issue FOLLOW_START — the walk and the wake-word call —
 * so this adapter no longer knows the owner. It parses the envelope and hands
 * the result to {@link FollowResultRouter}, the same shape
 * {@code NavigationResultHandler} already uses for NAVIGATION_RESULT.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class FollowResultHandler implements MqttMessageHandler {

    private final FollowResultRouter router;

    public FollowResultHandler(FollowResultRouter router) {
        this.router = router;
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
        router.route(
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
