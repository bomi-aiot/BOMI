package com.ssafy.bomi.mqtt.inbound;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.mqtt.config.BomiMqttProperties;
import org.junit.jupiter.api.Test;
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.acks.SimpleAcknowledgment;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class MqttInboundEndpointTest {

    private final BomiMqttProperties properties = new BomiMqttProperties();
    private final MqttInboundMessageParser parser =
        new MqttInboundMessageParser(new ObjectMapper());
    private final MqttInboundDispatcher dispatcher = mock(MqttInboundDispatcher.class);
    private final MqttInboundEndpoint endpoint =
        new MqttInboundEndpoint(properties, parser, dispatcher);

    @Test
    void acknowledgesAfterValidMessageIsDispatched() {
        SimpleAcknowledgment acknowledgment = mock(SimpleAcknowledgment.class);
        Message<String> message = message("""
            {
              "eventId": "event-01",
              "type": "DOOR_OPENED",
              "occurredAt": "2026-07-21T10:30:00+09:00",
              "sourceId": "door-01",
              "payload": {}
            }
            """, acknowledgment);

        endpoint.receive(message);

        verify(dispatcher).dispatch(any(MqttInboundMessage.class));
        verify(acknowledgment).acknowledge();
    }

    @Test
    void acknowledgesAndDiscardsContractViolation() {
        SimpleAcknowledgment acknowledgment = mock(SimpleAcknowledgment.class);
        Message<String> message = message("{not-json}", acknowledgment);

        endpoint.receive(message);

        verify(dispatcher, never()).dispatch(any());
        verify(acknowledgment).acknowledge();
    }

    @Test
    void doesNotAcknowledgeTransientDispatcherFailure() {
        SimpleAcknowledgment acknowledgment = mock(SimpleAcknowledgment.class);
        Message<String> message = message("""
            {
              "eventId": "event-01",
              "type": "DOOR_OPENED",
              "occurredAt": "2026-07-21T10:30:00+09:00",
              "sourceId": "door-01",
              "payload": {}
            }
            """, acknowledgment);
        doThrow(new IllegalStateException("temporary failure"))
            .when(dispatcher)
            .dispatch(any(MqttInboundMessage.class));

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> endpoint.receive(message))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("temporary failure");
        verify(acknowledgment, never()).acknowledge();
    }

    private static Message<String> message(
        String payload,
        SimpleAcknowledgment acknowledgment
    ) {
        return MessageBuilder
            .withPayload(payload)
            .setHeader(MqttHeaders.RECEIVED_TOPIC, "bomi/v1/iot/door-01/events")
            .setHeader(MqttHeaders.RECEIVED_QOS, 1)
            .setHeader(MqttHeaders.RECEIVED_RETAINED, false)
            .setHeader(
                IntegrationMessageHeaderAccessor.ACKNOWLEDGMENT_CALLBACK,
                acknowledgment
            )
            .build();
    }
}
