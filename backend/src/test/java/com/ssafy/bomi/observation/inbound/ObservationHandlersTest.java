package com.ssafy.bomi.observation.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.JsonNode;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.observation.application.RobotObservationService;
import com.ssafy.bomi.scenario.application.WellnessCheckOrchestrator;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.Test;

class ObservationHandlersTest {

    private final RobotObservationService service = mock(RobotObservationService.class);
    private final WellnessCheckOrchestrator wellnessOrchestrator = mock(WellnessCheckOrchestrator.class);

    private MqttInboundMessage message(MqttInboundCategory category, String type, String sourceId) {
        JsonNode body = null;
        return new MqttInboundMessage(
            category, "bomi/v1/topic", sourceId, "evt-01", type, OffsetDateTime.now(), 1, false, body);
    }

    @Test
    void restStateHandlerSupportsAndDelegates() {
        RestStateChangedHandler handler = new RestStateChangedHandler(service);

        MqttInboundMessage msg =
            message(MqttInboundCategory.ROBOT_STATUS, "REST_STATE_CHANGED", "robot-01");
        assertThat(handler.supports(msg)).isTrue();
        assertThat(handler.supports(
            message(MqttInboundCategory.ROBOT_STATUS, "NAVIGATION_STATUS", "robot-01"))).isFalse();

        handler.handle(msg);
        verify(service).recordRestState("robot-01", msg.body());
    }

    @Test
    void ambientHandlerSupportsAndDelegates() {
        AmbientObservedHandler handler = new AmbientObservedHandler(service, wellnessOrchestrator);

        MqttInboundMessage msg =
            message(MqttInboundCategory.IOT_EVENT, "AMBIENT_ENVIRONMENT_OBSERVED", "ambient-sensor-01");
        assertThat(handler.supports(msg)).isTrue();
        assertThat(handler.supports(
            message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", "x"))).isFalse();

        handler.handle(msg);
        verify(service).recordAmbient("ambient-sensor-01", msg.body());
        verify(wellnessOrchestrator).onAmbientObserved("ambient-sensor-01", msg.body());
    }

    @Test
    void navigationStatusHandlerSupportsAndDoesNotThrow() {
        NavigationStatusHandler handler = new NavigationStatusHandler();

        MqttInboundMessage msg =
            message(MqttInboundCategory.ROBOT_STATUS, "NAVIGATION_STATUS", "robot-01");
        assertThat(handler.supports(msg)).isTrue();
        assertThat(handler.supports(
            message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_STATUS", "x"))).isFalse();

        handler.handle(msg); // telemetry: logs only, must not throw
    }
}
