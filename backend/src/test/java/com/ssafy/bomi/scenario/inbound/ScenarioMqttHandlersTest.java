package com.ssafy.bomi.scenario.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.conversation.domain.ConversationOutcome;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import com.ssafy.bomi.scenario.application.NavigationResultRouter;
import com.ssafy.bomi.scenario.application.WakeWordCallOrchestrator;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ScenarioMqttHandlersTest {

    private static final OffsetDateTime OCCURRED_AT =
        OffsetDateTime.parse("2026-08-05T10:00:00+09:00");

    private final HomecomingOrchestrator orchestrator = mock(HomecomingOrchestrator.class);
    private final NavigationResultRouter navigationResultRouter =
        mock(NavigationResultRouter.class);
    private final WakeWordCallOrchestrator wakeWordCallOrchestrator =
        mock(WakeWordCallOrchestrator.class);
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void doorOpenedHandlerStartsHomecomingWithSensorId() {
        DoorOpenedHandler handler = new DoorOpenedHandler(orchestrator);
        MqttInboundMessage doorOpened = message(
            MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", "door-sensor-01",
            null, null, null, false, null);

        assertThat(handler.supports(doorOpened)).isTrue();
        handler.handle(doorOpened);

        verify(orchestrator).startHomecoming("door-sensor-01");
    }

    @Test
    void navigationResultHandlerDelegatesEveryV1ResultFieldOnce() {
        NavigationResultHandler handler = new NavigationResultHandler(navigationResultRouter);
        UUID scenarioId = UUID.randomUUID();
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("outcome", "FAILED");
        payload.put("resultCode", "NOT_ARRIVED");
        payload.put("reasonCode", "PATH_BLOCKED");

        MqttInboundMessage result = message(
            MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", "robot-01",
            scenarioId, null, "cmd-nav", false, body);

        assertThat(handler.supports(result)).isTrue();
        handler.handle(result);

        verify(navigationResultRouter, times(1)).route(
            scenarioId, "robot-01", "cmd-nav", false,
            "FAILED", "NOT_ARRIVED", "PATH_BLOCKED");
    }

    @Test
    void navigationResultHandlerMapsLegacyCancelledStatus() {
        NavigationResultHandler handler = new NavigationResultHandler(navigationResultRouter);
        UUID scenarioId = UUID.randomUUID();
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("scenarioId", scenarioId.toString());
        payload.put("status", "CANCELLED");

        handler.handle(message(
            MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", "robot-01",
            scenarioId, null, null, true, body));

        verify(navigationResultRouter).route(
            scenarioId, "robot-01", null, true,
            "CANCELLED", "NOT_ARRIVED", null);
    }

    @Test
    void wakeWordDetectedHandlerPassesTheCompleteTriggerToItsOrchestrator() {
        WakeWordDetectedHandler handler = new WakeWordDetectedHandler(wakeWordCallOrchestrator);
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("keyword", "보미야");
        payload.put("confidence", 0.92);
        MqttInboundMessage wakeWord = new MqttInboundMessage(
            MqttInboundCategory.ROBOT_EVENT,
            "bomi/v1/robot/robot-01/events",
            "robot-01",
            "evt-wake-01",
            "WAKE_WORD_DETECTED",
            OCCURRED_AT,
            1,
            false,
            null,
            null,
            null,
            false,
            body);

        assertThat(handler.supports(wakeWord)).isTrue();
        handler.handle(wakeWord);

        verify(wakeWordCallOrchestrator, times(1)).onWakeWordDetected(
            "robot-01", "evt-wake-01", OCCURRED_AT, "보미야", 0.92);
    }

    @Test
    void conversationStartedHandlerPassesAllCorrelationIds() {
        ConversationStartedHandler handler = new ConversationStartedHandler(orchestrator);
        UUID scenarioId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        ObjectNode body = objectMapper.createObjectNode();
        body.putObject("payload").put("intent", "HOMECOMING_GREETING");

        handler.handle(message(
            MqttInboundCategory.ROBOT_EVENT, "CONVERSATION_STARTED", "robot-01",
            scenarioId, conversationId, "cmd-ai", false, body));

        verify(orchestrator).onConversationStarted(
            scenarioId, conversationId, "cmd-ai", "robot-01",
            ConversationIntent.HOMECOMING_GREETING, OCCURRED_AT);
    }

    @Test
    void conversationEndedHandlerPassesOutcomeAndReason() {
        ConversationEndedHandler handler = new ConversationEndedHandler(orchestrator);
        UUID scenarioId = UUID.randomUUID();
        UUID conversationId = UUID.randomUUID();
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("outcome", "FAILED");
        payload.put("reasonCode", "AI_PROVIDER_ERROR");

        handler.handle(message(
            MqttInboundCategory.ROBOT_EVENT, "CONVERSATION_ENDED", "robot-01",
            scenarioId, conversationId, null, false, body));

        verify(orchestrator).onConversationEnded(
            scenarioId, conversationId, "robot-01", ConversationOutcome.FAILED,
            "AI_PROVIDER_ERROR", OCCURRED_AT);
    }

    @Test
    void doorClosedHandlerAcceptsAndDoesNotThrow() {
        DoorClosedHandler handler = new DoorClosedHandler();
        MqttInboundMessage doorClosed = message(
            MqttInboundCategory.IOT_EVENT, "DOOR_CLOSED", "door-sensor-01",
            null, null, null, false, null);

        assertThat(handler.supports(doorClosed)).isTrue();
        handler.handle(doorClosed);
    }

    private MqttInboundMessage message(
        MqttInboundCategory category,
        String type,
        String sourceId,
        UUID scenarioId,
        UUID conversationId,
        String commandId,
        boolean legacy,
        JsonNode body
    ) {
        return new MqttInboundMessage(
            category, "bomi/v1/topic", sourceId, "evt-01", type, OCCURRED_AT, 1, false,
            scenarioId, conversationId, commandId, legacy, body);
    }
}
