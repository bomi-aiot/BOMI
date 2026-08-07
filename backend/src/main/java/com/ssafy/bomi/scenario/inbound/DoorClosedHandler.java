package com.ssafy.bomi.scenario.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for a door-close IoT event.
 *
 * <p>{@code DOOR_CLOSED} carries no direction information by itself — the robot's own
 * HTTP forwarding path ({@code RobotDoorEventController}) already treats it as "accepted,
 * no action" for exactly that reason. This handler makes the MQTT path agree. Before this,
 * the type was not in {@code MqttInboundMessageParser}'s allow-list, so every DOOR_CLOSED
 * the IoT side actually sends was discarded as a <em>contract violation</em> even though
 * it is expected, valid traffic — the wrong signal for "this event carries no scenario
 * work" (a "no handler; ignoring" info log, which is what a type with a registered handler
 * but no side effect below would produce instead).</p>
 *
 * <p>No scenario or occupancy state changes here. If a future ticket wants DOOR_CLOSED for
 * something (closing out an "OUT" passage window, health-checking the sensor), this is the
 * seam to extend.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class DoorClosedHandler implements MqttMessageHandler {

    private static final Logger log = LoggerFactory.getLogger(DoorClosedHandler.class);
    private static final String TYPE_DOOR_CLOSED = "DOOR_CLOSED";

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.IOT_EVENT
            && TYPE_DOOR_CLOSED.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        log.debug("door closed: sensorId={}", message.sourceId());
    }
}
