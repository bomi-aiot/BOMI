package com.ssafy.bomi.observation.inbound;

import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.inbound.MqttMessageHandler;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * Inbound adapter for robot navigation progress ({@code ROBOT_STATUS} /
 * {@code NAVIGATION_STATUS}).
 *
 * <p>This is transient telemetry — the authoritative scenario/robot state is
 * driven by NAVIGATION_RESULT and the scenario lifecycle. For the MVP it is
 * acknowledged and logged; richer progress handling can be added when a payload
 * contract exists.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class NavigationStatusHandler implements MqttMessageHandler {

    private static final Logger log = LoggerFactory.getLogger(NavigationStatusHandler.class);
    private static final String TYPE_NAVIGATION_STATUS = "NAVIGATION_STATUS";

    @Override
    public boolean supports(MqttInboundMessage message) {
        return message.category() == MqttInboundCategory.ROBOT_STATUS
            && TYPE_NAVIGATION_STATUS.equals(message.type());
    }

    @Override
    public void handle(MqttInboundMessage message) {
        log.info("Navigation status from robot={}, eventId={}", message.sourceId(), message.eventId());
    }
}
