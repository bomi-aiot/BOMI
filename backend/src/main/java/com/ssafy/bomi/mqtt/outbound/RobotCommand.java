package com.ssafy.bomi.mqtt.outbound;

import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Set;
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

    private static final Set<String> NAVIGATION_TARGETS = Set.of(
        "LIVING_ROOM", "ENTRANCE", "DEFAULT");

    public RobotCommand {
        commandId = requireOpaqueId(commandId, "commandId");
        scenarioId = requireNonNull(scenarioId, "scenarioId");
        robotId = requireText(robotId, "robotId");
        type = requireNonNull(type, "type");
        occurredAt = requireNonNull(occurredAt, "occurredAt");
        expiresAt = requireNonNull(expiresAt, "expiresAt");
        payload = payload == null ? Map.of() : Map.copyOf(payload);

        if (type == RobotCommandType.NAVIGATE) {
            validateNavigatePayload(payload);
        }
        if (type == RobotCommandType.CANCEL) {
            validateCancelPayload(payload);
        }
        if ((type == RobotCommandType.FOLLOW_START || type == RobotCommandType.FOLLOW_STOP)
            && !payload.isEmpty()) {
            throw new IllegalArgumentException(type + " payload must be an empty object");
        }

        if (!expiresAt.isAfter(occurredAt)) {
            throw new IllegalArgumentException("expiresAt must be after occurredAt");
        }
    }

    private static void validateNavigatePayload(Map<String, Object> payload) {
        if (payload.size() != 1 || !payload.containsKey("target")) {
            throw new IllegalArgumentException(
                "NAVIGATE payload must contain exactly one 'target' field");
        }
        Object target = payload.get("target");
        if (!(target instanceof String) || !NAVIGATION_TARGETS.contains(target)) {
            throw new IllegalArgumentException(
                "NAVIGATE target must be one of LIVING_ROOM, ENTRANCE or DEFAULT");
        }
    }

    private static void validateCancelPayload(Map<String, Object> payload) {
        if (payload.size() != 2
            || !payload.containsKey("targetCommandId")
            || !payload.containsKey("reasonCode")) {
            throw new IllegalArgumentException(
                "CANCEL payload must contain exactly targetCommandId and reasonCode");
        }
        requireOpaqueId(asString(payload.get("targetCommandId"), "targetCommandId"),
            "targetCommandId");
        requireOpaqueId(asString(payload.get("reasonCode"), "reasonCode"), "reasonCode");
    }

    private static String asString(Object value, String field) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException(field + " must be a string");
        }
        return text;
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
