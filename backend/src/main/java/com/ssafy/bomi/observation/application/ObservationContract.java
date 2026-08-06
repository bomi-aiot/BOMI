package com.ssafy.bomi.observation.application;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;

/**
 * Single source of truth for rest/ambient observation <b>payload</b> field names.
 *
 * <p>As with {@code HomecomingContract}, the envelope is fixed by the team topic
 * convention; only the field names inside {@code payload} are our assumption
 * until the robot/IoT teams finalize the contract. Change them here (one place).</p>
 */
public final class ObservationContract {

    public static final String PAYLOAD_KEY = "payload";

    // REST_STATE_CHANGED payload
    public static final String REST_STATE_KEY = "restState";
    public static final String REST_STATE_RESTING = "RESTING";
    public static final String REST_STATE_AWAKE = "AWAKE";

    // AMBIENT_ENVIRONMENT_OBSERVED payload
    public static final String TEMPERATURE_KEY = "temperatureC";
    public static final String HUMIDITY_KEY = "humidityPercent";
    public static final String COMFORT_KEY = "comfortAssessment";
    public static final String OBSERVED_AT_KEY = "observedAt";

    private ObservationContract() {
    }

    /** Returns the {@code payload} object node, or throws if absent/not an object. */
    public static JsonNode payload(JsonNode body) {
        JsonNode payload = body == null ? null : body.get(PAYLOAD_KEY);
        if (payload == null || !payload.isObject()) {
            throw new IllegalArgumentException("Observation message has no payload object");
        }
        return payload;
    }

    public static String requiredText(JsonNode payload, String key) {
        JsonNode node = payload.get(key);
        if (node == null || !node.isTextual() || node.textValue().isBlank()) {
            throw new IllegalArgumentException("Missing payload field: " + key);
        }
        return node.textValue();
    }

    /** Optional numeric field as {@link BigDecimal}, or {@code null} if absent. */
    public static BigDecimal optionalDecimal(JsonNode payload, String key) {
        JsonNode node = payload.get(key);
        if (node == null || node.isNull() || !node.isNumber()) {
            return null;
        }
        return node.decimalValue();
    }

    /** Optional ISO-8601 timestamp, or {@code null} if absent/blank. */
    public static OffsetDateTime optionalTimestamp(JsonNode payload, String key) {
        JsonNode node = payload.get(key);
        if (node == null || !node.isTextual() || node.textValue().isBlank()) {
            return null;
        }
        try {
            return OffsetDateTime.parse(node.textValue());
        } catch (DateTimeParseException ex) {
            throw new IllegalArgumentException("payload field '" + key + "' must be ISO-8601", ex);
        }
    }
}
