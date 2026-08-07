package com.ssafy.bomi.scenario.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.FollowResultRouter;
import com.ssafy.bomi.scenario.application.WalkOrchestrator;
import com.ssafy.bomi.scenario.application.WalkRequest;
import com.ssafy.bomi.scenario.domain.WalkAction;
import com.ssafy.bomi.scenario.domain.WalkRequestIngress;
import com.ssafy.bomi.scenario.domain.WalkRequestSource;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class WalkMqttHandlersTest {

    private static final OffsetDateTime OCCURRED_AT =
        OffsetDateTime.parse("2026-08-05T16:00:00+09:00");

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final WalkOrchestrator orchestrator = mock(WalkOrchestrator.class);
    private final FollowResultRouter followResultRouter = mock(FollowResultRouter.class);

    @Test
    void walkRequestedHandlerDelegatesTheCompleteTransportNeutralRequestOnce() {
        WalkRequestedHandler handler = new WalkRequestedHandler(orchestrator);
        UUID conversationId = UUID.randomUUID();
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("action", "START");
        payload.put("source", "VOICE");
        MqttInboundMessage request = message(
            MqttInboundCategory.ROBOT_EVENT,
            "WALK_REQUESTED",
            "evt-walk-start",
            null,
            conversationId,
            null,
            body);

        assertThat(handler.supports(request)).isTrue();
        assertThat(handler.supports(message(
            MqttInboundCategory.ROBOT_RESULT,
            "WALK_REQUESTED",
            "evt-wrong-category",
            null,
            null,
            null,
            body))).isFalse();
        handler.handle(request);

        ArgumentCaptor<WalkRequest> captor = ArgumentCaptor.forClass(WalkRequest.class);
        verify(orchestrator, times(1)).handleRequest(captor.capture());
        assertThat(captor.getValue()).isEqualTo(new WalkRequest(
            WalkRequestIngress.MQTT,
            "evt-walk-start",
            "robot-01",
            WalkAction.START,
            WalkRequestSource.VOICE,
            conversationId,
            OCCURRED_AT));
    }

    @Test
    void followResultHandlerDelegatesEveryCorrelationAndResultFieldOnce() {
        FollowResultHandler handler = new FollowResultHandler(followResultRouter);
        UUID scenarioId = UUID.randomUUID();
        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("outcome", "FAILED");
        payload.put("resultCode", "STOPPED");
        payload.put("reasonCode", "PERSON_LOST");
        MqttInboundMessage result = message(
            MqttInboundCategory.ROBOT_RESULT,
            "FOLLOW_RESULT",
            "evt-follow-result",
            scenarioId,
            null,
            "cmd-follow-start",
            body);

        assertThat(handler.supports(result)).isTrue();
        assertThat(handler.supports(message(
            MqttInboundCategory.ROBOT_RESULT,
            "NAVIGATION_RESULT",
            "evt-nav",
            scenarioId,
            null,
            "cmd-follow-start",
            body))).isFalse();
        handler.handle(result);

        // 핸들러는 봉투를 풀어 라우터에 넘기기만 한다. 어느 시나리오가
        // 주인인지는 FollowResultRouter 가 정한다(FollowResultRouterTest 참고).
        verify(followResultRouter, times(1)).route(
            "evt-follow-result",
            scenarioId,
            "robot-01",
            "cmd-follow-start",
            OCCURRED_AT,
            "FAILED",
            "STOPPED",
            "PERSON_LOST");
    }

    private static MqttInboundMessage message(
        MqttInboundCategory category,
        String type,
        String eventId,
        UUID scenarioId,
        UUID conversationId,
        String commandId,
        ObjectNode body
    ) {
        return new MqttInboundMessage(
            category,
            "bomi/v1/robot/robot-01/" +
                (category == MqttInboundCategory.ROBOT_RESULT ? "results" : "events"),
            "robot-01",
            eventId,
            type,
            OCCURRED_AT,
            1,
            false,
            scenarioId,
            conversationId,
            commandId,
            false,
            body);
    }
}
