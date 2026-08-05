package com.ssafy.bomi.mqtt.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class MqttInboundMessageParserTest {

    private final MqttInboundMessageParser parser =
        new MqttInboundMessageParser(new ObjectMapper());

    @Test
    void parsesIoTEventAndPreservesOpaqueEventId() {
        String payload = """
            {
              "eventId": "01K0M4Y7G1D8W3A9H2T6Q5R4NP",
              "type": "PRESENCE_DETECTED",
              "occurredAt": "2026-07-21T10:30:00+09:00",
              "sourceId": "entrance-hub-01",
              "payload": {"direction": "INBOUND"}
            }
            """;

        MqttInboundMessage message = parser.parse(
            "bomi/v1/iot/entrance-hub-01/events", payload, 1, false);

        assertThat(message.category()).isEqualTo(MqttInboundCategory.IOT_EVENT);
        assertThat(message.eventId()).isEqualTo("01K0M4Y7G1D8W3A9H2T6Q5R4NP");
        assertThat(message.sourceId()).isEqualTo("entrance-hub-01");
    }

    @Test
    void parsesV1NavigationResultWithTopLevelCorrelation() {
        UUID scenarioId = UUID.randomUUID();
        String payload = """
            {
              "eventId": "evt-nav-01",
              "commandId": "cmd-nav-01",
              "scenarioId": "%s",
              "robotId": "robot-01",
              "type": "NAVIGATION_RESULT",
              "occurredAt": "2026-07-21T10:30:15+09:00",
              "payload": {
                "outcome": "SUCCEEDED",
                "resultCode": "ARRIVED",
                "reasonCode": null
              }
            }
            """.formatted(scenarioId);

        MqttInboundMessage message = parser.parse(
            "bomi/v1/robot/robot-01/results", payload, 1, false);

        assertThat(message.requireScenarioId()).isEqualTo(scenarioId);
        assertThat(message.requireCommandId()).isEqualTo("cmd-nav-01");
        assertThat(message.legacyContract()).isFalse();
    }

    @Test
    void temporarilyParsesLegacyNavigationResult() {
        UUID scenarioId = UUID.randomUUID();
        String payload = """
            {
              "eventId": "evt-nav-legacy",
              "robotId": "robot-01",
              "type": "NAVIGATION_RESULT",
              "occurredAt": "2026-07-21T10:30:15+09:00",
              "payload": {"scenarioId": "%s", "status": "ARRIVED"}
            }
            """.formatted(scenarioId);

        MqttInboundMessage message = parser.parse(
            "bomi/v1/robot/robot-01/results", payload, 1, false);

        assertThat(message.requireScenarioId()).isEqualTo(scenarioId);
        assertThat(message.commandId()).isNull();
        assertThat(message.legacyContract()).isTrue();
    }

    @Test
    void rejectsMixedV1AndLegacyNavigationResult() {
        String scenarioId = UUID.randomUUID().toString();
        String payload = """
            {
              "eventId": "evt-nav-mixed",
              "commandId": "cmd-nav-01",
              "scenarioId": "%s",
              "robotId": "robot-01",
              "type": "NAVIGATION_RESULT",
              "occurredAt": "2026-07-21T10:30:15+09:00",
              "payload": {"scenarioId": "%s", "status": "ARRIVED"}
            }
            """.formatted(scenarioId, scenarioId);

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/results", payload, 1, false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("must not mix");
    }

    @Test
    void parsesConversationStartedAndEnded() {
        UUID scenarioId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        String started = """
            {
              "eventId": "evt-started",
              "commandId": "cmd-conversation-01",
              "scenarioId": "%s",
              "conversationId": "%s",
              "robotId": "robot-01",
              "type": "CONVERSATION_STARTED",
              "occurredAt": "2026-08-05T10:00:01+09:00",
              "payload": {"intent": "HOMECOMING_GREETING"}
            }
            """.formatted(scenarioId, conversationId);
        MqttInboundMessage startedMessage = parser.parse(
            "bomi/v1/robot/robot-01/events", started, 1, false);
        assertThat(startedMessage.requireScenarioId()).isEqualTo(scenarioId);
        assertThat(startedMessage.requireConversationId()).isEqualTo(conversationId);
        assertThat(startedMessage.requireCommandId()).isEqualTo("cmd-conversation-01");

        String ended = """
            {
              "eventId": "evt-ended",
              "scenarioId": "%s",
              "conversationId": "%s",
              "robotId": "robot-01",
              "type": "CONVERSATION_ENDED",
              "occurredAt": "2026-08-05T10:01:00+09:00",
              "payload": {"outcome": "FAILED", "reasonCode": "AI_PROVIDER_ERROR"}
            }
            """.formatted(scenarioId, conversationId);
        MqttInboundMessage endedMessage = parser.parse(
            "bomi/v1/robot/robot-01/events", ended, 1, false);
        assertThat(endedMessage.requireConversationId()).isEqualTo(conversationId);
    }

    @Test
    void rejectsInvalidResultAndConversationReasonRules() {
        String invalidResult = """
            {
              "eventId": "evt-nav-invalid",
              "commandId": "cmd-nav-01",
              "scenarioId": "%s",
              "robotId": "robot-01",
              "type": "NAVIGATION_RESULT",
              "occurredAt": "2026-08-05T10:00:01+09:00",
              "payload": {
                "outcome": "FAILED",
                "resultCode": "NOT_ARRIVED",
                "reasonCode": null
              }
            }
            """.formatted(UUID.randomUUID());
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/results", invalidResult, 1, false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("reasonCode");

        String invalidEnd = """
            {
              "eventId": "evt-ended-invalid",
              "scenarioId": "%s",
              "conversationId": "%s",
              "robotId": "robot-01",
              "type": "CONVERSATION_ENDED",
              "occurredAt": "2026-08-05T10:01:00+09:00",
              "payload": {"outcome": "FAILED", "reasonCode": null}
            }
            """.formatted(UUID.randomUUID(), UUID.randomUUID());
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/events", invalidEnd, 1, false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("requires a reasonCode");
    }

    @Test
    void rejectsSourceMismatchRetainedMalformedAndUnknownType() {
        String valid = """
            {
              "eventId": "event-01",
              "type": "DOOR_OPENED",
              "occurredAt": "2026-07-21T10:30:00+09:00",
              "sourceId": "door-01",
              "payload": {}
            }
            """;

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/iot/different-device/events", valid, 1, false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("does not match");
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/iot/door-01/events", valid, 1, true))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("retain=false");
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/iot/door-01/events", "{not-json}", 1, false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("valid UTF-8 JSON");

        String unknown = valid.replace("DOOR_OPENED", "UNKNOWN_EVENT");
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/iot/door-01/events", unknown, 1, false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("Unsupported MQTT type");
    }

    @Test
    void acceptsExistingMotionAndDoorClosedEvents() {
        for (String type : new String[] {"MOTION_DETECTED", "DOOR_CLOSED"}) {
            String payload = """
                {
                  "eventId": "event-%s",
                  "type": "%s",
                  "occurredAt": "2026-08-04T02:36:55+09:00",
                  "sourceId": "door-sensor-01",
                  "payload": {}
                }
                """.formatted(type, type);
            assertThat(parser.parse(
                "bomi/v1/iot/door-sensor-01/events", payload, 1, false).type())
                .isEqualTo(type);
        }
    }
}
