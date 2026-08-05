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
import java.util.UUID;
import org.springframework.stereotype.Component;

@Component
public class MqttInboundMessageParser {

    private static final int MAX_OPAQUE_ID_LENGTH = 64;
    private static final Set<String> NAVIGATION_REASON_CODES = Set.of(
        "COMMAND_EXPIRED", "UNKNOWN_TARGET", "PATH_BLOCKED", "LOCALIZATION_LOST",
        "EXECUTION_TIMEOUT", "SAFETY_STOP", "INTERNAL_ERROR");
    // PRESENCE_DETECTED: 초기 계약의 방향-판정 이벤트. IoT는 이제 DOOR_OPENED +
    // MOTION_DETECTED(현관 PIR)로 직접 보낸다 (S15P11E102-226). 아직 이 타입을 보내는
    // 배포가 남아있을 수 있어 당장 제거하지 않고 허용 목록에 남겨둔다 — 지워도 되는지는
    // IoT 쪽에서 완전히 넘어온 뒤 별도로 확인한다.
    private static final Map<MqttInboundCategory, Set<String>> ALLOWED_TYPES = Map.of(
        MqttInboundCategory.IOT_EVENT,
        Set.of("DOOR_OPENED", "MOTION_DETECTED", "DOOR_CLOSED", "PRESENCE_DETECTED",
            "AMBIENT_ENVIRONMENT_OBSERVED"),
        MqttInboundCategory.ROBOT_EVENT,
        Set.of("ONBOARDING_ANSWER_CAPTURED", "WAKE_WORD_DETECTED",
            "CONVERSATION_STARTED", "CONVERSATION_ENDED"),
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

        Correlation correlation = validateTypeSpecific(body, type);

        return new MqttInboundMessage(
            topicMatch.category(),
            topic,
            topicMatch.sourceId(),
            eventId,
            type,
            occurredAt,
            qos,
            false,
            correlation.scenarioId(),
            correlation.conversationId(),
            correlation.commandId(),
            correlation.legacyContract(),
            body
        );
    }

    private static Correlation validateTypeSpecific(JsonNode body, String type) {
        return switch (type) {
            case "NAVIGATION_RESULT" -> validateNavigationResult(body);
            case "WAKE_WORD_DETECTED" -> validateWakeWordDetected(body);
            case "CONVERSATION_STARTED" -> validateConversationStarted(body);
            case "CONVERSATION_ENDED" -> validateConversationEnded(body);
            default -> new Correlation(
                optionalUuid(body, "scenarioId"),
                optionalUuid(body, "conversationId"),
                optionalText(body, "commandId", MAX_OPAQUE_ID_LENGTH),
                false);
        };
    }

    private static Correlation validateWakeWordDetected(JsonNode body) {
        for (String field : new String[] {"scenarioId", "conversationId", "commandId"}) {
            if (body.has(field)) {
                throw new MqttContractViolationException(
                    "WAKE_WORD_DETECTED must not include correlation field '" + field + "'");
            }
        }
        rejectUnexpectedFields(body,
            Set.of("eventId", "robotId", "type", "occurredAt", "payload"),
            "WAKE_WORD_DETECTED envelope");

        JsonNode payload = body.get("payload");
        rejectUnexpectedFields(payload, Set.of("keyword", "confidence"),
            "WAKE_WORD_DETECTED payload");
        requiredText(payload, "keyword", 20);

        if (payload.has("confidence")) {
            JsonNode confidence = payload.get("confidence");
            if (!confidence.isNumber()) {
                throw new MqttContractViolationException(
                    "MQTT payload field 'confidence' must be a number between 0 and 1");
            }
            double value = confidence.doubleValue();
            if (!Double.isFinite(value) || value < 0 || value > 1) {
                throw new MqttContractViolationException(
                    "MQTT payload field 'confidence' must be between 0 and 1");
            }
        }

        return new Correlation(null, null, null, false);
    }

    private static void rejectUnexpectedFields(
        JsonNode object,
        Set<String> allowed,
        String location
    ) {
        object.fieldNames().forEachRemaining(field -> {
            if (!allowed.contains(field)) {
                throw new MqttContractViolationException(
                    location + " contains unsupported field '" + field + "'");
            }
        });
    }

    private static Correlation validateNavigationResult(JsonNode body) {
        JsonNode payload = body.get("payload");
        boolean hasV1 = body.has("scenarioId") || body.has("commandId");
        boolean hasLegacy = payload.has("scenarioId") || payload.has("status");
        if (hasV1 && hasLegacy) {
            throw new MqttContractViolationException(
                "NAVIGATION_RESULT must not mix v1 and legacy fields");
        }
        if (!hasV1) {
            UUID scenarioId = requiredUuid(payload, "scenarioId", "payload.scenarioId");
            String status = requiredText(payload, "status", 32);
            if (!Set.of("ARRIVED", "FAILED", "CANCELLED").contains(status)) {
                throw new MqttContractViolationException(
                    "Unsupported legacy NAVIGATION_RESULT status '" + status + "'");
            }
            return new Correlation(scenarioId, null, null, true);
        }

        UUID scenarioId = requiredUuid(body, "scenarioId", "scenarioId");
        String commandId = requiredText(body, "commandId", MAX_OPAQUE_ID_LENGTH);
        String outcome = requiredText(payload, "outcome", 32);
        String resultCode = requiredText(payload, "resultCode", 32);
        if (!Set.of("SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT").contains(outcome)) {
            throw new MqttContractViolationException(
                "Unsupported NAVIGATION_RESULT outcome '" + outcome + "'");
        }
        if (!Set.of("ARRIVED", "NOT_ARRIVED").contains(resultCode)) {
            throw new MqttContractViolationException(
                "Unsupported NAVIGATION_RESULT resultCode '" + resultCode + "'");
        }
        String reasonCode = requiredNullableReason(payload);
        if (reasonCode != null && !NAVIGATION_REASON_CODES.contains(reasonCode)) {
            throw new MqttContractViolationException(
                "Unsupported NAVIGATION_RESULT reasonCode '" + reasonCode + "'");
        }
        if ("SUCCEEDED".equals(outcome)) {
            if (!"ARRIVED".equals(resultCode) || reasonCode != null) {
                throw new MqttContractViolationException(
                    "Successful NAVIGATION_RESULT must be ARRIVED with reasonCode=null");
            }
        } else if (!"NOT_ARRIVED".equals(resultCode) || reasonCode == null) {
            throw new MqttContractViolationException(
                "Unsuccessful NAVIGATION_RESULT must be NOT_ARRIVED with a reasonCode");
        }
        return new Correlation(scenarioId, null, commandId, false);
    }

    private static Correlation validateConversationStarted(JsonNode body) {
        UUID scenarioId = requiredUuid(body, "scenarioId", "scenarioId");
        UUID conversationId = requiredUuid(body, "conversationId", "conversationId");
        String commandId = requiredText(body, "commandId", MAX_OPAQUE_ID_LENGTH);
        String intent = requiredText(body.get("payload"), "intent", 64);
        if (!Set.of("WELLNESS_CHECK", "MEDICATION_REMINDER", "HOMECOMING_GREETING")
            .contains(intent)) {
            throw new MqttContractViolationException(
                "Unsupported CONVERSATION_STARTED intent '" + intent + "'");
        }
        return new Correlation(scenarioId, conversationId, commandId, false);
    }

    private static Correlation validateConversationEnded(JsonNode body) {
        UUID scenarioId = requiredUuid(body, "scenarioId", "scenarioId");
        UUID conversationId = requiredUuid(body, "conversationId", "conversationId");
        JsonNode payload = body.get("payload");
        String outcome = requiredText(payload, "outcome", 32);
        if (!Set.of("COMPLETED", "NO_RESPONSE", "CANCELLED", "FAILED").contains(outcome)) {
            throw new MqttContractViolationException(
                "Unsupported CONVERSATION_ENDED outcome '" + outcome + "'");
        }
        String reasonCode = requiredNullableReason(payload);
        if ("FAILED".equals(outcome) && reasonCode == null) {
            throw new MqttContractViolationException(
                "FAILED CONVERSATION_ENDED requires a reasonCode");
        }
        return new Correlation(scenarioId, conversationId, null, false);
    }

    private static String requiredNullableReason(JsonNode payload) {
        if (!payload.has("reasonCode")) {
            throw new MqttContractViolationException(
                "MQTT payload field 'reasonCode' is required and may be null");
        }
        JsonNode reason = payload.get("reasonCode");
        if (reason == null || reason.isNull()) {
            return null;
        }
        if (!reason.isTextual() || reason.textValue().isBlank()) {
            throw new MqttContractViolationException(
                "MQTT payload field 'reasonCode' must be null or a non-blank string");
        }
        if (reason.textValue().length() > 100) {
            throw new MqttContractViolationException(
                "MQTT payload field 'reasonCode' exceeds 100 characters");
        }
        return reason.textValue();
    }

    private static UUID requiredUuid(JsonNode body, String field, String displayName) {
        String value = requiredText(body, field, 36);
        try {
            return UUID.fromString(value);
        } catch (IllegalArgumentException ex) {
            throw new MqttContractViolationException(
                "MQTT payload field '" + displayName + "' must be a UUID", ex);
        }
    }

    private static UUID optionalUuid(JsonNode body, String field) {
        if (body == null || !body.has(field)) {
            return null;
        }
        return requiredUuid(body, field, field);
    }

    private static String optionalText(JsonNode body, String field, int maxLength) {
        if (body == null || !body.has(field)) {
            return null;
        }
        return requiredText(body, field, maxLength);
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

    private record Correlation(
        UUID scenarioId,
        UUID conversationId,
        String commandId,
        boolean legacyContract
    ) {
    }
}
