package com.ssafy.bomi.scenario.inbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.ssafy.bomi.mqtt.inbound.MqttInboundMessage;
import com.ssafy.bomi.mqtt.topic.MqttInboundCategory;
import com.ssafy.bomi.scenario.application.HomecomingOrchestrator;
import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ScenarioMqttHandlersTest {

    private final HomecomingOrchestrator orchestrator = mock(HomecomingOrchestrator.class);
    private final ObjectMapper objectMapper = new ObjectMapper();

    private MqttInboundMessage message(
        MqttInboundCategory category, String type, JsonNode body, String sourceId) {
        return new MqttInboundMessage(
            category, "bomi/v1/topic", sourceId, "evt-01", type, OffsetDateTime.now(), 1, false, body);
    }

    @Test
    void doorOpenedHandlerStartsHomecomingWithSensorId() {
        DoorOpenedHandler handler = new DoorOpenedHandler(orchestrator);

        MqttInboundMessage doorOpened =
            message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", null, "door-sensor-01");
        assertThat(handler.supports(doorOpened)).isTrue();
        assertThat(handler.supports(
            message(MqttInboundCategory.ROBOT_RESULT, "DOOR_OPENED", null, "x"))).isFalse();
        assertThat(handler.supports(
            message(MqttInboundCategory.IOT_EVENT, "PRESENCE_DETECTED", null, "x"))).isFalse();

        handler.handle(doorOpened);
        verify(orchestrator).startHomecoming("door-sensor-01");
    }

    @Test
    void navigationResultHandlerAdvancesScenarioFromEchoedId() {
        NavigationResultHandler handler = new NavigationResultHandler(orchestrator);
        UUID scenarioId = UUID.randomUUID();

        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("scenarioId", scenarioId.toString());
        payload.put("status", "ARRIVED");
        MqttInboundMessage result =
            message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", body, "robot-01");

        assertThat(handler.supports(result)).isTrue();
        assertThat(handler.supports(
            message(MqttInboundCategory.ROBOT_STATUS, "NAVIGATION_RESULT", null, "x"))).isFalse();

        handler.handle(result);
        verify(orchestrator).onRobotArrived(scenarioId);
    }

    @Test
    void navigationResultHandlerFailsScenarioOnFailedStatus() {
        NavigationResultHandler handler = new NavigationResultHandler(orchestrator);
        UUID scenarioId = UUID.randomUUID();

        ObjectNode body = objectMapper.createObjectNode();
        ObjectNode payload = body.putObject("payload");
        payload.put("scenarioId", scenarioId.toString());
        payload.put("status", "FAILED");

        handler.handle(
            message(MqttInboundCategory.ROBOT_RESULT, "NAVIGATION_RESULT", body, "robot-01"));
        verify(orchestrator).onNavigationFailed(scenarioId);
    }

    @Test
    void doorClosedHandlerAcceptsAndDoesNotThrow() {
        DoorClosedHandler handler = new DoorClosedHandler();

        MqttInboundMessage doorClosed =
            message(MqttInboundCategory.IOT_EVENT, "DOOR_CLOSED", null, "door-sensor-01");
        assertThat(handler.supports(doorClosed)).isTrue();
        assertThat(handler.supports(
            message(MqttInboundCategory.IOT_EVENT, "DOOR_OPENED", null, "door-sensor-01"))).isFalse();

        handler.handle(doorClosed); // no side effects to verify; must simply not throw
    }

}
