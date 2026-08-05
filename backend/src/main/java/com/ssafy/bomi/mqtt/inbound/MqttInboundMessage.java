package com.ssafy.bomi.mqtt.inbound;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import java.time.OffsetDateTime;
import java.util.UUID;

public record MqttInboundMessage(
    MqttInboundCategory category,
    String topic,
    String sourceId,
    String eventId,
    String type,
    OffsetDateTime occurredAt,
    int qos,
    boolean retained,
    UUID scenarioId,
    UUID conversationId,
    String commandId,
    boolean legacyContract,
    JsonNode body
) {

    /** Backward-compatible constructor for messages that carry no correlation IDs. */
    public MqttInboundMessage(
        MqttInboundCategory category,
        String topic,
        String sourceId,
        String eventId,
        String type,
        OffsetDateTime occurredAt,
        int qos,
        boolean retained,
        JsonNode body
    ) {
        this(category, topic, sourceId, eventId, type, occurredAt, qos, retained,
            null, null, null, false, body);
    }

    public JsonNode payload() {
        return body == null ? null : body.get("payload");
    }

    public UUID requireScenarioId() {
        if (scenarioId == null) {
            throw new IllegalArgumentException("MQTT message has no scenarioId: " + type);
        }
        return scenarioId;
    }

    public UUID requireConversationId() {
        if (conversationId == null) {
            throw new IllegalArgumentException("MQTT message has no conversationId: " + type);
        }
        return conversationId;
    }

    public String requireCommandId() {
        if (commandId == null || commandId.isBlank()) {
            throw new IllegalArgumentException("MQTT message has no commandId: " + type);
        }
        return commandId;
    }
}
