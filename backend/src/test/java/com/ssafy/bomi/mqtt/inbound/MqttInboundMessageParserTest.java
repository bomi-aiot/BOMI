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
                "reasonCode": null,
                "location": "LIVING_ROOM",
                "message": "arrived"
              }
            }
            """.formatted(scenarioId);

        MqttInboundMessage message = parser.parse(
            "bomi/v1/robot/robot-01/results", payload, 1, false);

        assertThat(message.requireScenarioId()).isEqualTo(scenarioId);
        assertThat(message.requireCommandId()).isEqualTo("cmd-nav-01");
        assertThat(message.payload().path("location").asText()).isEqualTo("LIVING_ROOM");
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
    void rejectsV1NavigationResultFieldsOutsideTheFinalSchema() {
        UUID scenarioId = UUID.randomUUID();
        String correlation = "\"commandId\": \"cmd-nav-01\", \"scenarioId\": \""
            + scenarioId + "\"";

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/results",
            v1NavigationResult(correlation,
                "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"ARRIVED\", "
                    + "\"reasonCode\": null",
                "\"conversationId\": \"" + UUID.randomUUID() + "\""),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("unsupported field 'conversationId'");

        for (String invalidPayload : new String[] {
            "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"ARRIVED\", "
                + "\"reasonCode\": null, \"pose\": {}",
            "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"ARRIVED\", "
                + "\"reasonCode\": null, \"location\": \"KITCHEN\"",
            "\"outcome\": \"FAILED\", \"resultCode\": \"NOT_ARRIVED\", "
                + "\"reasonCode\": \"PATH_BLOCKED\", \"location\": \"ENTRANCE\"",
            "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"ARRIVED\", "
                + "\"reasonCode\": null, \"message\": 7"
        }) {
            assertThatThrownBy(() -> parser.parse(
                "bomi/v1/robot/robot-01/results",
                v1NavigationResult(correlation, invalidPayload, null),
                1,
                false))
                .isInstanceOf(MqttContractViolationException.class);
        }
    }

    @Test
    void requiresFinalV1NavigationResultCorrelationAndResultFields() {
        UUID scenarioId = UUID.randomUUID();
        String validPayload = "\"outcome\": \"SUCCEEDED\", "
            + "\"resultCode\": \"ARRIVED\", \"reasonCode\": null";

        for (String invalidResult : new String[] {
            v1NavigationResult("\"commandId\": \"cmd-nav-01\"", validPayload, null),
            v1NavigationResult("\"scenarioId\": \"" + scenarioId + "\"",
                validPayload, null),
            v1NavigationResult(
                "\"commandId\": \"cmd-nav-01\", \"scenarioId\": \"not-a-uuid\"",
                validPayload, null),
            v1NavigationResult(
                "\"commandId\": \"   \", \"scenarioId\": \"" + scenarioId + "\"",
                validPayload, null),
            v1NavigationResult(
                "\"commandId\": \"cmd-nav-01\", \"scenarioId\": \"" + scenarioId + "\"",
                validPayload, null).replace("\"robotId\": \"robot-01\",", ""),
            v1NavigationResult(
                "\"commandId\": \"cmd-nav-01\", \"scenarioId\": \"" + scenarioId + "\"",
                validPayload, null).replace("\"eventId\": \"evt-nav-v1\",", ""),
            v1NavigationResult(
                "\"commandId\": \"cmd-nav-01\", \"scenarioId\": \"" + scenarioId + "\"",
                "\"outcome\": \"DONE\", \"resultCode\": \"ARRIVED\", "
                    + "\"reasonCode\": null", null),
            v1NavigationResult(
                "\"commandId\": \"cmd-nav-01\", \"scenarioId\": \"" + scenarioId + "\"",
                "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"RUNNING\", "
                    + "\"reasonCode\": null", null),
            v1NavigationResult(
                "\"commandId\": \"cmd-nav-01\", \"scenarioId\": \"" + scenarioId + "\"",
                "\"outcome\": \"FAILED\", \"resultCode\": \"NOT_ARRIVED\"", null)
        }) {
            assertThatThrownBy(() -> parser.parse(
                "bomi/v1/robot/robot-01/results", invalidResult, 1, false))
                .isInstanceOf(MqttContractViolationException.class);
        }

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-02/results",
            v1NavigationResult(
                "\"commandId\": \"cmd-nav-01\", \"scenarioId\": \"" + scenarioId + "\"",
                validPayload, null),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("does not match");
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
    void parsesWakeWordDetectedWithValidEnvelope() {
        MqttInboundMessage withConfidence = parser.parse(
            "bomi/v1/robot/robot-01/events",
            wakeWordEvent(null, "\"keyword\": \"보미야\", \"confidence\": 0.92"),
            1,
            false);

        assertThat(withConfidence.category()).isEqualTo(MqttInboundCategory.ROBOT_EVENT);
        assertThat(withConfidence.type()).isEqualTo("WAKE_WORD_DETECTED");
        assertThat(withConfidence.sourceId()).isEqualTo("robot-01");
        assertThat(withConfidence.payload().path("keyword").asText()).isEqualTo("보미야");
        assertThat(withConfidence.scenarioId()).isNull();
        assertThat(withConfidence.conversationId()).isNull();
        assertThat(withConfidence.commandId()).isNull();

        assertThat(parser.parse(
            "bomi/v1/robot/robot-01/events",
            wakeWordEvent(null, "\"keyword\": \"보미야\""),
            1,
            false).type()).isEqualTo("WAKE_WORD_DETECTED");
    }

    @Test
    void validatesWakeWordKeyword() {
        for (String invalidPayload : new String[] {
            "",
            "\"keyword\": \"   \"",
            "\"keyword\": \"123456789012345678901\""
        }) {
            assertThatThrownBy(() -> parser.parse(
                "bomi/v1/robot/robot-01/events",
                wakeWordEvent(null, invalidPayload),
                1,
                false))
                .isInstanceOf(MqttContractViolationException.class)
                .hasMessageContaining("keyword");
        }
    }

    @Test
    void validatesOptionalWakeWordConfidence() {
        for (String validConfidence : new String[] {"0", "1"}) {
            assertThat(parser.parse(
                "bomi/v1/robot/robot-01/events",
                wakeWordEvent(null,
                    "\"keyword\": \"보미야\", \"confidence\": " + validConfidence),
                1,
                false).type()).isEqualTo("WAKE_WORD_DETECTED");
        }

        for (String invalidConfidence : new String[] {"\"0.9\"", "-0.01", "1.01", "null"}) {
            assertThatThrownBy(() -> parser.parse(
                "bomi/v1/robot/robot-01/events",
                wakeWordEvent(null,
                    "\"keyword\": \"보미야\", \"confidence\": " + invalidConfidence),
                1,
                false))
                .isInstanceOf(MqttContractViolationException.class)
                .hasMessageContaining("confidence");
        }
    }

    @Test
    void rejectsCorrelationIdsOnWakeWordTrigger() {
        for (String correlation : new String[] {
            "\"scenarioId\": \"" + UUID.randomUUID() + "\"",
            "\"conversationId\": \"" + UUID.randomUUID() + "\"",
            "\"commandId\": \"cmd-wake-01\""
        }) {
            assertThatThrownBy(() -> parser.parse(
                "bomi/v1/robot/robot-01/events",
                wakeWordEvent(correlation, "\"keyword\": \"보미야\""),
                1,
                false))
                .isInstanceOf(MqttContractViolationException.class)
                .hasMessageContaining("must not include correlation field");
        }
    }

    @Test
    void rejectsWakeWordFieldsOutsideTheFinalAsyncApiSchema() {
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/events",
            wakeWordEvent("\"rawAudio\": \"forbidden\"", "\"keyword\": \"보미야\""),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("unsupported field 'rawAudio'");

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/events",
            wakeWordEvent(null,
                "\"keyword\": \"보미야\", \"fullStt\": \"보미야 오늘 뭐 해\""),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("unsupported field 'fullStt'");
    }

    @Test
    void rejectsWakeWordWhenTopicRobotDoesNotMatchEnvelopeRobot() {
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-02/events",
            wakeWordEvent(null, "\"keyword\": \"bomi\""),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("does not match");
    }

    @Test
    void parsesWalkRequestedWithStrictStartAndStopEnvelopes() {
        UUID conversationId = UUID.randomUUID();
        MqttInboundMessage start = parser.parse(
            "bomi/v1/robot/robot-01/events",
            walkRequested(
                "\"conversationId\": \"" + conversationId + "\"",
                "\"action\": \"START\", \"source\": \"VOICE\""),
            1,
            false);

        assertThat(start.type()).isEqualTo("WALK_REQUESTED");
        assertThat(start.conversationId()).isEqualTo(conversationId);
        assertThat(start.scenarioId()).isNull();
        assertThat(start.commandId()).isNull();
        assertThat(start.payload().path("action").asText()).isEqualTo("START");

        MqttInboundMessage stop = parser.parse(
            "bomi/v1/robot/robot-01/events",
            walkRequested(null, "\"action\": \"STOP\", \"source\": \"APP\""),
            1,
            false);
        assertThat(stop.conversationId()).isNull();
        assertThat(stop.payload().path("source").asText()).isEqualTo("APP");
    }

    @Test
    void rejectsInvalidWalkRequestedFieldsAndEnums() {
        for (String payloadFields : new String[] {
            "\"source\": \"VOICE\"",
            "\"action\": \"START\"",
            "\"action\": \"PAUSE\", \"source\": \"VOICE\"",
            "\"action\": \"START\", \"source\": \"ROBOT\""
        }) {
            assertThatThrownBy(() -> parser.parse(
                "bomi/v1/robot/robot-01/events",
                walkRequested(null, payloadFields),
                1,
                false))
                .isInstanceOf(MqttContractViolationException.class);
        }

        for (String forbiddenCorrelation : new String[] {
            "\"scenarioId\": \"" + UUID.randomUUID() + "\"",
            "\"commandId\": \"cmd-follow-start\""
        }) {
            assertThatThrownBy(() -> parser.parse(
                "bomi/v1/robot/robot-01/events",
                walkRequested(forbiddenCorrelation,
                    "\"action\": \"START\", \"source\": \"VOICE\""),
                1,
                false))
                .isInstanceOf(MqttContractViolationException.class)
                .hasMessageContaining("field");
        }

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/events",
            walkRequested("\"conversationId\": \"not-a-uuid\"",
                "\"action\": \"START\", \"source\": \"VOICE\""),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("conversationId");

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/events",
            walkRequested("\"conversationId\": \"1-1-1-1-1\"",
                "\"action\": \"START\", \"source\": \"VOICE\""),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("conversationId");

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/events",
            walkRequested("\"unexpected\": true",
                "\"action\": \"START\", \"source\": \"VOICE\""),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("unsupported field 'unexpected'");

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/events",
            walkRequested(null,
                "\"action\": \"START\", \"source\": \"VOICE\", \"trackId\": \"x\""),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("unsupported field 'trackId'");
    }

    @Test
    void parsesFollowResultWithRequiredCorrelationAndReasonRules() {
        UUID scenarioId = UUID.randomUUID();
        MqttInboundMessage started = parser.parse(
            "bomi/v1/robot/robot-01/results",
            followResult(scenarioId, "cmd-follow-start",
                "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"STARTED\", "
                    + "\"reasonCode\": null"),
            1,
            false);

        assertThat(started.type()).isEqualTo("FOLLOW_RESULT");
        assertThat(started.requireScenarioId()).isEqualTo(scenarioId);
        assertThat(started.requireCommandId()).isEqualTo("cmd-follow-start");
        assertThat(started.legacyContract()).isFalse();

        for (String outcome : new String[] {"FAILED", "CANCELLED", "TIMED_OUT"}) {
            MqttInboundMessage terminal = parser.parse(
                "bomi/v1/robot/robot-01/results",
                followResult(scenarioId, "cmd-follow-start",
                    "\"outcome\": \"" + outcome + "\", \"resultCode\": \"STOPPED\", "
                        + "\"reasonCode\": \"PERSON_LOST\", \"message\": \"lost\""),
                1,
                false);
            assertThat(terminal.payload().path("outcome").asText()).isEqualTo(outcome);
        }

        for (String reasonCode : new String[] {
            "PERSON_LOST",
            "COMMAND_EXPIRED",
            "EXECUTION_TIMEOUT",
            "SAFETY_STOP",
            "INTERNAL_ERROR"
        }) {
            assertThat(parser.parse(
                "bomi/v1/robot/robot-01/results",
                followResult(scenarioId, "cmd-follow-start",
                    "\"outcome\": \"FAILED\", \"resultCode\": \"STOPPED\", "
                        + "\"reasonCode\": \"" + reasonCode + "\""),
                1,
                false).payload().path("reasonCode").asText()).isEqualTo(reasonCode);
        }

        assertThat(parser.parse(
            "bomi/v1/robot/robot-01/results",
            followResult(scenarioId, "cmd-follow-stop",
                "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"UNCHANGED\", "
                    + "\"reasonCode\": null"),
            1,
            false).payload().path("resultCode").asText()).isEqualTo("UNCHANGED");
    }

    @Test
    void rejectsInvalidFollowResultContract() {
        UUID scenarioId = UUID.randomUUID();
        for (String invalidPayload : new String[] {
            "\"outcome\": \"DONE\", \"resultCode\": \"STARTED\", \"reasonCode\": null",
            "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"RUNNING\", \"reasonCode\": null",
            "\"outcome\": \"SUCCEEDED\", \"resultCode\": \"STARTED\", "
                + "\"reasonCode\": \"INTERNAL_ERROR\"",
            "\"outcome\": \"FAILED\", \"resultCode\": \"STOPPED\", \"reasonCode\": null",
            "\"outcome\": \"FAILED\", \"resultCode\": \"STOPPED\", "
                + "\"reasonCode\": \"UNKNOWN_FAILURE\"",
            "\"outcome\": \"FAILED\", \"resultCode\": \"STOPPED\", "
                + "\"reasonCode\": \"PERSON_LOST\", \"message\": 123",
            "\"outcome\": \"FAILED\", \"resultCode\": \"STOPPED\", "
                + "\"reasonCode\": \"PERSON_LOST\", \"boundingBox\": []"
        }) {
            assertThatThrownBy(() -> parser.parse(
                "bomi/v1/robot/robot-01/results",
                followResult(scenarioId, "cmd-follow", invalidPayload),
                1,
                false))
                .isInstanceOf(MqttContractViolationException.class);
        }

        String validPayload = "\"outcome\": \"SUCCEEDED\", "
            + "\"resultCode\": \"STOPPED\", \"reasonCode\": null";
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/results",
            followResultWithTopLevel("\"commandId\": \"cmd-follow\"", validPayload),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("scenarioId");
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/results",
            followResultWithTopLevel("\"scenarioId\": \"" + scenarioId + "\"", validPayload),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("commandId");
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/results",
            followResultWithTopLevel(
                "\"scenarioId\": \"not-a-uuid\", \"commandId\": \"cmd-follow\"",
                validPayload),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("scenarioId");
        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-02/results",
            followResult(scenarioId, "cmd-follow", validPayload),
            1,
            false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("does not match");
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

    @Test
    void rejectsNavigationReasonOutsideTheAsyncApiEnum() {
        String invalidResult = """
            {
              "eventId": "evt-nav-reason-invalid",
              "commandId": "cmd-nav-01",
              "scenarioId": "%s",
              "robotId": "robot-01",
              "type": "NAVIGATION_RESULT",
              "occurredAt": "2026-08-05T10:00:01+09:00",
              "payload": {
                "outcome": "FAILED",
                "resultCode": "NOT_ARRIVED",
                "reasonCode": "FREE_FORM_FAILURE"
              }
            }
            """.formatted(UUID.randomUUID());

        assertThatThrownBy(() -> parser.parse(
            "bomi/v1/robot/robot-01/results", invalidResult, 1, false))
            .isInstanceOf(MqttContractViolationException.class)
            .hasMessageContaining("Unsupported NAVIGATION_RESULT reasonCode");
    }

    private static String wakeWordEvent(String extraTopLevelField, String payloadFields) {
        String extra = extraTopLevelField == null ? "" : extraTopLevelField + ",";
        return """
            {
              "eventId": "evt-wake-01",
              "type": "WAKE_WORD_DETECTED",
              "occurredAt": "2026-08-05T10:30:00+09:00",
              "robotId": "robot-01",
              %s
              "payload": {%s}
            }
            """.formatted(extra, payloadFields);
    }

    private static String v1NavigationResult(
        String correlationFields,
        String payloadFields,
        String extraTopLevelField
    ) {
        String extra = extraTopLevelField == null ? "" : ",\n" + extraTopLevelField;
        return """
            {
              "eventId": "evt-nav-v1",
              %s,
              "robotId": "robot-01",
              "type": "NAVIGATION_RESULT",
              "occurredAt": "2026-08-05T10:30:00+09:00",
              "payload": {%s}%s
            }
            """.formatted(correlationFields, payloadFields, extra);
    }

    private static String walkRequested(String extraTopLevelField, String payloadFields) {
        String extra = extraTopLevelField == null ? "" : extraTopLevelField + ",";
        return """
            {
              "eventId": "evt-walk-01",
              "type": "WALK_REQUESTED",
              "occurredAt": "2026-08-05T16:00:00+09:00",
              "robotId": "robot-01",
              %s
              "payload": {%s}
            }
            """.formatted(extra, payloadFields);
    }

    private static String followResult(
        UUID scenarioId,
        String commandId,
        String payloadFields
    ) {
        return followResultWithTopLevel(
            "\"scenarioId\": \"" + scenarioId + "\", "
                + "\"commandId\": \"" + commandId + "\"",
            payloadFields);
    }

    private static String followResultWithTopLevel(
        String correlationFields,
        String payloadFields
    ) {
        return """
            {
              "eventId": "evt-follow-result-01",
              %s,
              "type": "FOLLOW_RESULT",
              "occurredAt": "2026-08-05T16:00:03+09:00",
              "robotId": "robot-01",
              "payload": {%s}
            }
            """.formatted(correlationFields, payloadFields);
    }
}
