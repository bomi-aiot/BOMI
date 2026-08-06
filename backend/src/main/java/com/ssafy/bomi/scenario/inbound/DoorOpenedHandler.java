package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for a door-open IoT event: starts the homecoming scenario.
 *
 * <p>The topic {@code sourceId} is the door-sensor device id, which the
 * orchestrator maps to a senior via configuration.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class DoorOpenedHandler implements MqttMessageHandler {

    private static final String TYPE_DOOR_OPENED = "DOOR_OPENED";

    private final HomecomingOrchestrator orchestrator;

    public DoorOpenedHandler(HomecomingOrchestrator orchestrator) {
        this.orchestrator = orchestrator;
    }

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.IOT_EVENT
            && TYPE_DOOR_OPENED.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        orchestrator.startHomecoming(message.sourceId());
    }
}
