package com.ssafy.bomi.mqtt.inbound;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Processes each inbound MQTT message exactly once and routes it to the
 * {@link MqttMessageHandler}s that declare support for it.
 *
 * <p>Idempotency: MQTT QoS 1 is at-least-once, so the same {@code eventId} may
 * arrive more than once. Before routing, the dispatcher reserves the
 * {@code eventId} via {@link ProcessedEventStore}; a duplicate is skipped. If a
 * handler fails, the reservation is released so a redelivery can be retried
 * (the reservation only "sticks" on success).</p>
 *
 * <p>Routing: every handler whose
 * {@link MqttMessageHandler#supports(MqttInboundMessage)} returns {@code true}
 * is invoked. Messages with no matching handler are logged and ignored (they
 * were already validated and acknowledged at the transport boundary).</p>
 *
 * <p>Scope: concrete handlers and scenario transitions are implemented by
 * follow-up tickets.</p>
 */
@Component
public class MqttInboundDispatcher {

    private static final Logger log = LoggerFactory.getLogger(MqttInboundDispatcher.class);

    private final List<MqttMessageHandler> handlers;
    private final ProcessedEventStore processedEventStore;

    public MqttInboundDispatcher(
        List<MqttMessageHandler> handlers,
        ProcessedEventStore processedEventStore
    ) {
        this.handlers = List.copyOf(handlers);
        this.processedEventStore = processedEventStore;
    }

    public void dispatch(MqttInboundMessage message) {
        if (!processedEventStore.tryAcquire(message.eventId())) {
            log.info(
                "Duplicate MQTT message; skipping: category={}, type={}, eventId={}",
                message.category(),
                message.type(),
                message.eventId()
            );
            return;
        }

        try {
            route(message);
        } catch (RuntimeException ex) {
            // Handling failed: release the reservation so a QoS-1 redelivery retries.
            processedEventStore.release(message.eventId());
            throw ex;
        }
    }

    private void route(MqttInboundMessage message) {
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
