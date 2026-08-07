package com.ssafy.bomi.mqtt.inbound;

import com.ssafy.bomi.mqtt.config.BomiMqttProperties;
import com.ssafy.bomi.mqtt.config.MqttChannels;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.integration.StaticMessageHeaderAccessor;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class MqttInboundEndpoint {

    private static final Logger log = LoggerFactory.getLogger(MqttInboundEndpoint.class);

    private final BomiMqttProperties properties;
    private final MqttInboundMessageParser parser;
    private final MqttInboundDispatcher dispatcher;

    public MqttInboundEndpoint(
        BomiMqttProperties properties,
        MqttInboundMessageParser parser,
        MqttInboundDispatcher dispatcher
    ) {
        this.properties = properties;
        this.parser = parser;
        this.dispatcher = dispatcher;
    }

    @ServiceActivator(inputChannel = MqttChannels.INBOUND)
    public void receive(Message<?> message) {
        String topic = message.getHeaders().get(MqttHeaders.RECEIVED_TOPIC, String.class);

        try {
            int qos = intHeader(message, MqttHeaders.RECEIVED_QOS);
            boolean retained = booleanHeader(message, MqttHeaders.RECEIVED_RETAINED);
            String payload = payloadAsString(message.getPayload());
            if (qos != properties.getQos()) {
                throw new MqttContractViolationException(
                    "MQTT inbound QoS must be " + properties.getQos() + " but was " + qos
                );
            }
            MqttInboundMessage inbound = parser.parse(topic, payload, qos, retained);
            dispatcher.dispatch(inbound);
            acknowledge(message);
        } catch (MqttContractViolationException ex) {
            log.warn(
                "Discarding invalid MQTT message: topic={}, reason={}",
                topic,
                ex.getMessage()
            );
            acknowledge(message);
        } catch (RuntimeException ex) {
            log.error("MQTT message processing failed before acknowledgment: topic={}", topic, ex);
            throw ex;
        }
    }

    private static String payloadAsString(Object payload) {
        if (payload instanceof String text) {
            return text;
        }
        if (payload instanceof byte[] bytes) {
            return new String(bytes, java.nio.charset.StandardCharsets.UTF_8);
        }
        throw new MqttContractViolationException(
            "MQTT payload must be a UTF-8 string or byte array"
        );
    }

    private static int intHeader(Message<?> message, String name) {
        Integer value = message.getHeaders().get(name, Integer.class);
        if (value == null) {
            throw new MqttContractViolationException("Missing MQTT header: " + name);
        }
        return value;
    }

    private static boolean booleanHeader(Message<?> message, String name) {
        Boolean value = message.getHeaders().get(name, Boolean.class);
        if (value == null) {
            throw new MqttContractViolationException("Missing MQTT header: " + name);
        }
        return value;
    }

    private static void acknowledge(Message<?> message) {
        var acknowledgment = StaticMessageHeaderAccessor.getAcknowledgment(message);
        if (acknowledgment != null) {
            acknowledgment.acknowledge();
        }
    }
}
