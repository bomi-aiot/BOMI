package com.ssafy.bomi.mqtt.inbound;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Extension point for MQTT business handlers.
 *
 * <p>This ticket only verifies and exposes the transport boundary. Scenario
 * transitions, persistence and idempotency are intentionally implemented by
 * follow-up handlers.</p>
 */
@Component
public class MqttInboundDispatcher {

    private static final Logger log = LoggerFactory.getLogger(MqttInboundDispatcher.class);

    public void dispatch(MqttInboundMessage message) {
        log.info(
            "MQTT message accepted: category={}, topic={}, eventId={}, type={}, occurredAt={}",
            message.category(),
            message.topic(),
            message.eventId(),
            message.type(),
            message.occurredAt()
        );
    }
}
