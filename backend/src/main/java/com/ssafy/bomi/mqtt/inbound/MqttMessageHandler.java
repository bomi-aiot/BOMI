package com.ssafy.bomi.mqtt.inbound;

/**
 * Business handler for a validated inbound MQTT message.
 *
 * <p>Each handler declares which messages it is interested in via
 * {@link #supports(MqttInboundMessage)} — typically by
 * {@link MqttInboundMessage#category()} and/or {@link MqttInboundMessage#type()}
 * — and processes them in {@link #handle(MqttInboundMessage)}. Implementations
 * should keep their {@code supports} predicates disjoint so a message maps to a
 * single handler; the {@link MqttInboundDispatcher} nonetheless delegates to
 * every matching handler.</p>
 *
 * <p>This ticket only wires the routing. Concrete handlers (scenario
 * orchestration, etc.) and idempotency are added by follow-up tickets.</p>
 */
public interface MqttMessageHandler {

    /** Returns {@code true} if this handler should process the given message. */
    boolean supports(MqttInboundMessage message);

    /** Processes a message that {@link #supports(MqttInboundMessage)} accepted. */
    void handle(MqttInboundMessage message);
}
