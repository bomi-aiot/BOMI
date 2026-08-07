package com.ssafy.bomi.scenario.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.conversation.domain.ConversationOutcome;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.occupancy.application.DoorEventService;
import com.ssafy.bomi.occupancy.application.EntranceDirectionResolver.Signal;
import com.ssafy.bomi.occupancy.config.EntranceProperties;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import com.ssafy.bomi.scenario.application.NavigationResultRouter;
import com.ssafy.bomi.scenario.application.WakeWordCallOrchestrator;
import com.ssafy.bomi.scenario.config.HomecomingProperties;
import java.time.OffsetDateTime;
import java.util.Optional;
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
    private final DoorEventService doorEventService = mock(DoorEventService.class);
    private final HomecomingProperties homecomingProperties = mock(HomecomingProperties.class);
    private final EntranceProperties entranceProperties = new EntranceProperties();
    private final ObjectMapper objectMapper = new ObjectMapper();

    private DoorOpenedHandler doorOpenedHandler() {
        return new DoorOpenedHandler(
            orchestrator, doorEventService, homecomingProperties, entranceProperties);
    }

    /**
     * 기본 경로. 방향을 묻지 않고 문이 열렸다는 사실만으로 귀가를 시작한다 —
     * PIR 배치가 검증되기 전까지의 동작이며, 시연 대본이 의존하는 동작이다.
     */
    @Test
    void doorOpenedHandlerStartsHomecomingWithSensorIdWhenResolutionIsOff() {
        MqttInboundMessage doorOpened = message(
            MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", "door-sensor-01",
            null, null, null, false, null);

        assertThat(entranceProperties.isDirectionResolutionEnabled()).isFalse();
        assertThat(doorOpenedHandler().supports(doorOpened)).isTrue();
        doorOpenedHandler().handle(doorOpened);

        verify(orchestrator).startHomecoming("door-sensor-01");
        verifyNoInteractions(doorEventService);
    }

    /**
     * 스위치를 켜면 문 신호가 PIR 과 같은 버퍼로 들어간다.
     *
     * <p>여기서 오케스트레이터를 직접 부르지 <b>않는</b> 것이 핵심이다. 짝이 맞아
     * 방향이 확정될 때 {@code DoorEventService} 가 인사와 함께 부른다 — 문만 열리고
     * 아무도 지나가지 않았다면 로봇은 움직이지 않아야 한다.</p>
     */
    @Test
    void doorOpenedHandlerFeedsDirectionResolutionWhenEnabled() {
        entranceProperties.setDirectionResolutionEnabled(true);
        UUID seniorId = UUID.randomUUID();
        when(homecomingProperties.findSenior("door-sensor-01")).thenReturn(Optional.of(seniorId));

        doorOpenedHandler().handle(message(
            MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", "door-sensor-01",
            null, null, null, false, null));

        verify(doorEventService).accept(
            eq(seniorId), eq(Signal.DOOR_OPENED), any(OffsetDateTime.class), isNull());
        verifyNoInteractions(orchestrator);
    }

    /**
     * 미등록 센서는 경고 후 폐기한다.
     *
     * <p>예외를 던지면 ack 가 생략되어 브로커가 QoS 1 로 무한 재전송하고, 센서 id
     * 오타 하나가 수신 파이프라인 전체를 막는다.</p>
     */
    @Test
    void doorOpenedHandlerDropsUnmappedSensorWhenResolutionEnabled() {
        entranceProperties.setDirectionResolutionEnabled(true);
        when(homecomingProperties.findSenior("unknown-door")).thenReturn(Optional.empty());

        doorOpenedHandler().handle(message(
            MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", "unknown-door",
            null, null, null, false, null));

        verifyNoInteractions(doorEventService);
        verifyNoInteractions(orchestrator);
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
