package com.ssafy.bomi.mqtt.inbound;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.mqtt.topic.MqttTopicMatch;
import com.ssafy.bomi.mqtt.topic.MqttTopics;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class MqttInboundMessageParser {

    private static final int MAX_OPAQUE_ID_LENGTH = 64;
    private static final Map<MqttInboundCategory, Set<String>> ALLOWED_TYPES = Map.of(
        MqttInboundCategory.IOT_EVENT,
        Set.of("DOOR_OPENED", "PRESENCE_DETECTED", "AMBIENT_ENVIRONMENT_OBSERVED"),
        MqttInboundCategory.ROBOT_EVENT,
        Set.of("ONBOARDING_ANSWER_CAPTURED", "CONVERSATION_ENDED"),
        MqttInboundCategory.ROBOT_STATUS,
        Set.of("REST_STATE_CHANGED", "NAVIGATION_STATUS"),
        MqttInboundCategory.ROBOT_RESULT,
        Set.of("NAVIGATION_RESULT", "SPEAK_RESULT", "CANCEL_RESULT")
    );

    private final ObjectMapper objectMapper;

    public MqttInboundMessageParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public MqttInboundMessage parse(
        String topic,
        String payload,
        int qos,
        boolean retained
    ) {
        MqttTopicMatch topicMatch = matchTopic(topic);
        JsonNode body = readObject(payload);

        String eventId = requiredText(body, "eventId", MAX_OPAQUE_ID_LENGTH);
        String type = requiredText(body, "type", 64);
        requireAllowedType(topicMatch.category(), type);
        OffsetDateTime occurredAt = requiredTimestamp(body, "occurredAt");
        requirePayloadObject(body);
        String payloadSourceId = topicMatch.category() == MqttInboundCategory.IOT_EVENT
            ? requiredText(body, "sourceId", 64)
            : requiredText(body, "robotId", 64);

        if (!topicMatch.sourceId().equals(payloadSourceId)) {
            throw new MqttContractViolationException(
                "MQTT topic sourceId does not match payload source identifier"
            );
        }
        if (retained) {
            throw new MqttContractViolationException(
                "BOMI MQTT inbound messages must use retain=false"
            );
        }

        return new MqttInboundMessage(
            topicMatch.category(),
            topic,
            topicMatch.sourceId(),
            eventId,
            type,
            occurredAt,
            qos,
            false,
            body
        );
    }

    private static MqttTopicMatch matchTopic(String topic) {
        try {
            return MqttTopics.matchInbound(topic);
        } catch (IllegalArgumentException ex) {
            throw new MqttContractViolationException(ex.getMessage(), ex);
        }
    }

    private JsonNode readObject(String payload) {
        if (payload == null || payload.isBlank()) {
            throw new MqttContractViolationException("MQTT payload must not be blank");
        }
        try {
            JsonNode body = objectMapper.readTree(payload);
            if (body == null || !body.isObject()) {
                throw new MqttContractViolationException(
                    "MQTT payload must be a JSON object"
                );
            }
            return body;
        } catch (JsonProcessingException ex) {
            throw new MqttContractViolationException(
                "MQTT payload must be valid UTF-8 JSON",
                ex
            );
        }
    }

    private static String requiredText(JsonNode body, String field, int maxLength) {
        JsonNode value = body.get(field);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw new MqttContractViolationException(
                "MQTT payload field '" + field + "' must be a non-blank string"
            );
        }
        String text = value.textValue();
        if (text.length() > maxLength) {
            throw new MqttContractViolationException(
                "MQTT payload field '" + field + "' exceeds " + maxLength + " characters"
            );
        }
        return text;
    }

    private static OffsetDateTime requiredTimestamp(JsonNode body, String field) {
        String value = requiredText(body, field, 64);
        try {
            return OffsetDateTime.parse(value);
        } catch (DateTimeParseException ex) {
            throw new MqttContractViolationException(
                "MQTT payload field '" + field + "' must be ISO 8601 with an offset",
                ex
            );
        }
    }

    private static void requireAllowedType(
        MqttInboundCategory category,
        String type
    ) {
        if (!ALLOWED_TYPES.get(category).contains(type)) {
            throw new MqttContractViolationException(
                "Unsupported MQTT type '" + type + "' for " + category
            );
        }
    }

    private static void requirePayloadObject(JsonNode body) {
        JsonNode payload = body.get("payload");
        if (payload == null || !payload.isObject()) {
            throw new MqttContractViolationException(
                "MQTT payload field 'payload' must be a JSON object"
            );
        }
    }
}
