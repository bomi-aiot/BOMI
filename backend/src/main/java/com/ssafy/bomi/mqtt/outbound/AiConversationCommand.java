package com.ssafy.bomi.mqtt.outbound;

import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.OffsetDateTime;
import java.util.UUID;

/** MQTT v1 command envelope sent from Backend to AI Chat. */
public record AiConversationCommand(
    String commandId,
    UUID scenarioId,
    UUID conversationId,
    String robotId,
    AiConversationCommandType type,
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    OffsetDateTime occurredAt,
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    OffsetDateTime expiresAt,
    StartConversationPayload payload
) {

    public AiConversationCommand {
        commandId = requireText(commandId, "commandId", 64);
        scenarioId = requireNonNull(scenarioId, "scenarioId");
        conversationId = requireNonNull(conversationId, "conversationId");
        robotId = requireText(robotId, "robotId", 64);
        type = requireNonNull(type, "type");
        occurredAt = requireNonNull(occurredAt, "occurredAt");
        expiresAt = requireNonNull(expiresAt, "expiresAt");
        payload = requireNonNull(payload, "payload");
        if (!expiresAt.isAfter(occurredAt)) {
            throw new IllegalArgumentException("expiresAt must be after occurredAt");
        }
    }

    private static String requireText(String value, String field, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        if (value.length() > maxLength) {
            throw new IllegalArgumentException(field + " must not exceed " + maxLength + " characters");
        }
        return value;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
