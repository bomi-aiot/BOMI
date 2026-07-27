package com.ssafy.bomi.mqtt.inbound;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Routes validated inbound MQTT messages to the {@link MqttMessageHandler}s that
 * declare support for them.
 *
 * <p>All handler beans are injected; on dispatch this finds every handler whose
 * {@link MqttMessageHandler#supports(MqttInboundMessage)} returns {@code true}
 * and delegates. Messages with no matching handler are logged and safely ignored
 * (they were already validated and acknowledged at the transport boundary).</p>
 *
 * <p>Scope: this ticket wires routing only. Concrete handlers, scenario
 * transitions, persistence and idempotency are implemented by follow-up
 * tickets.</p>
 */
@Component
public class MqttInboundDispatcher {

    private static final Logger log = LoggerFactory.getLogger(MqttInboundDispatcher.class);

    private final List<MqttMessageHandler> handlers;

    public MqttInboundDispatcher(List<MqttMessageHandler> handlers) {
        this.handlers = List.copyOf(handlers);
    }

    public void dispatch(MqttInboundMessage message) {
        List<MqttMessageHandler> matched = handlers.stream()
            .filter(handler -> handler.supports(message))
            .toList();

        if (matched.isEmpty()) {
            log.info(
                "No MQTT handler for message; ignoring: category={}, type={}, eventId={}",
                message.category(),
                message.type(),
                message.eventId()
            );
            return;
        }

        for (MqttMessageHandler handler : matched) {
            handler.handle(message);
        }
    }
}
