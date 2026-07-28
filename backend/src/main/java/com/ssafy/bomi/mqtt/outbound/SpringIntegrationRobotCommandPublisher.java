package com.ssafy.bomi.mqtt.outbound;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.ssafy.bomi.mqtt.config.BomiMqttProperties;
import com.ssafy.bomi.mqtt.config.MqttChannels;
import com.ssafy.bomi.mqtt.topic.MqttTopics;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class SpringIntegrationRobotCommandPublisher implements RobotCommandPublisher {

    private final MessageChannel outboundChannel;
    private final ObjectMapper objectMapper;
    private final BomiMqttProperties properties;

    public SpringIntegrationRobotCommandPublisher(
        @Qualifier(MqttChannels.OUTBOUND) MessageChannel outboundChannel,
        ObjectMapper objectMapper,
        BomiMqttProperties properties
    ) {
        this.outboundChannel = outboundChannel;
        this.objectMapper = objectMapper;
        this.properties = properties;
    }

    @Override
    public void publish(RobotCommand command) {
        if (command == null) {
            throw new IllegalArgumentException("command must not be null");
        }

        String topic = MqttTopics.robotCommands(command.robotId());
        Message<String> message = MessageBuilder
            .withPayload(toJson(command))
            .setHeader(MqttHeaders.TOPIC, topic)
            .setHeader(MqttHeaders.QOS, properties.getQos())
            .setHeader(MqttHeaders.RETAINED, false)
            .build();

        boolean accepted = outboundChannel.send(
            message,
            properties.getCompletionTimeout().toMillis()
        );
        if (!accepted) {
            throw new IllegalStateException(
                "MQTT outbound channel did not accept commandId=" + command.commandId()
            );
        }
    }

    private String toJson(RobotCommand command) {
        try {
            return objectMapper.writeValueAsString(command);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                "Robot command could not be serialized: commandId=" + command.commandId(),
                ex
            );
        }
    }
}
