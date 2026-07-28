package com.ssafy.bomi.mqtt.outbound;

import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

public record RobotCommand(
    String commandId,
    UUID scenarioId,
    String robotId,
    RobotCommandType type,
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    OffsetDateTime occurredAt,
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    OffsetDateTime expiresAt,
    Map<String, Object> payload
) {

    public RobotCommand {
        commandId = requireOpaqueId(commandId, "commandId");
        scenarioId = requireNonNull(scenarioId, "scenarioId");
        robotId = requireText(robotId, "robotId");
        type = requireNonNull(type, "type");
        occurredAt = requireNonNull(occurredAt, "occurredAt");
        expiresAt = requireNonNull(expiresAt, "expiresAt");
        payload = payload == null ? Map.of() : Map.copyOf(payload);

        if (!expiresAt.isAfter(occurredAt)) {
            throw new IllegalArgumentException("expiresAt must be after occurredAt");
        }
    }

    private static String requireOpaqueId(String value, String field) {
        String text = requireText(value, field);
        if (text.length() > 64) {
            throw new IllegalArgumentException(field + " must not exceed 64 characters");
        }
        return text;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
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
