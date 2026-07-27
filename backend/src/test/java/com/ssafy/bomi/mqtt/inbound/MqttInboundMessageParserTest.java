package com.ssafy.bomi.mqtt.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
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
            "bomi/v1/iot/entrance-hub-01/events",
            payload,
            1,
            false
        );

        assertThat(message.category()).isEqualTo(MqttInboundCategory.IOT_EVENT);
        assertThat(message.eventId()).isEqualTo("01K0M4Y7G1D8W3A9H2T6Q5R4NP");
        assertThat(message.sourceId()).isEqualTo("entrance-hub-01");
        assertThat(message.body().path("payload").path("direction").asText())
            .isEqualTo("INBOUND");
    }

    @Test
    void parsesRobotResult() {
        String payload = """
            {
              "eventId": "01K0M50D4S8V2X6Z1B3N7Q9RTP",
              "commandId": "01K0M4Y8B7F5M2N1Q9R6S3T8VX",
              "scenarioId": "6fd94c8c-3903-4a01-a82d-819e0c8edb12",
              "robotId": "robot-01",
              "type": "NAVIGATION_RESULT",
              "occurredAt": "2026-07-21T10:30:15+09:00",
              "payload": {"outcome": "ARRIVED"}
            }
            """;

        MqttInboundMessage message = parser.parse(
            "bomi/v1/robot/robot-01/results",
            payload,
            1,
            false
        );

        assertThat(message.category()).isEqualTo(MqttInboundCategory.ROBOT_RESULT);
        assertThat(message.type()).isEqualTo("NAVIGATION_RESULT");
    }

    @Test
    void rejectsSourceIdThatDoesNotMatchTopic() {
        String payload = """
            {
              "eventId": "event-01",
              "type": "DOOR_OPENED",
              "occurredAt": "2026-07-21T10:30:00+09:00",
              "sourceId": "different-device",
              "payload": {}
            }
            """;

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/iot/door-01/events",
            payload,
            1,
            false
        ))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("does not match");
    }

    @Test
    void rejectsRetainedOrMalformedMessages() {
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
            "bomi/v1/iot/door-01/events",
            valid,
            1,
            true
        ))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("retain=false");

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/iot/door-01/events",
            "{not-json}",
            1,
            false
        ))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("valid UTF-8 JSON");
    }

    @Test
    void rejectsUnknownTypeForTopicCategory() {
        String payload = """
            {
              "eventId": "event-01",
              "type": "UNKNOWN_EVENT",
              "occurredAt": "2026-07-21T10:30:00+09:00",
              "sourceId": "door-01",
              "payload": {}
            }
            """;

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/iot/door-01/events",
            payload,
            1,
            false
        ))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("Unsupported MQTT type");
    }
}
