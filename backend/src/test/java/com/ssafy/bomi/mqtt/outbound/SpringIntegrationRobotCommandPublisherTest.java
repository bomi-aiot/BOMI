package com.ssafy.bomi.mqtt.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.ssafy.bomi.mqtt.config.BomiMqttProperties;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.integration.mqtt.support.MqttHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

class SpringIntegrationRobotCommandPublisherTest {

    @Test
    void publishesJsonToRobotCommandTopicWithContractHeaders() throws Exception {
        MessageChannel channel = mock(MessageChannel.class);
        BomiMqttProperties properties = new BomiMqttProperties();
        when(channel.send(any(Message.class), eq(5_000L))).thenReturn(true);
        ObjectMapper objectMapper = new ObjectMapper().registerModule(new JavaTimeModule());
        SpringIntegrationRobotCommandPublisher publisher =
            new SpringIntegrationRobotCommandPublisher(channel, objectMapper, properties);
        UUID scenarioId = UUID.randomUUID();
        RobotCommand command = new RobotCommand(
            "command-opaque-01",
            scenarioId,
            "robot-01",
            RobotCommandType.NAVIGATE,
            OffsetDateTime.parse("2026-07-21T10:30:01+09:00"),
            OffsetDateTime.parse("2026-07-21T10:31:01+09:00"),
            Map.of("waypointId", "ENTRANCE")
        );

        publisher.publish(command);

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Message> captor = ArgumentCaptor.forClass(Message.class);
        verify(channel).send(captor.capture(), eq(5_000L));
        Message<?> message = captor.getValue();
        assertThat(message.getHeaders().get(MqttHeaders.TOPIC))
            .isEqualTo("bomi/v1/robot/robot-01/commands");
        assertThat(message.getHeaders().get(MqttHeaders.QOS)).isEqualTo(1);
        assertThat(message.getHeaders().get(MqttHeaders.RETAINED)).isEqualTo(false);

        com.fasterxml.jackson.databind.JsonNode json =
            objectMapper.readTree((String) message.getPayload());
        assertThat(json.path("commandId").asText()).isEqualTo("command-opaque-01");
        assertThat(json.path("scenarioId").asText()).isEqualTo(scenarioId.toString());
        assertThat(json.path("robotId").asText()).isEqualTo("robot-01");
        assertThat(json.path("type").asText()).isEqualTo("NAVIGATE");
        assertThat(json.path("occurredAt").asText())
            .isEqualTo("2026-07-21T10:30:01+09:00");
        assertThat(json.path("expiresAt").asText())
            .isEqualTo("2026-07-21T10:31:01+09:00");
        assertThat(json.path("payload").path("waypointId").asText())
            .isEqualTo("ENTRANCE");
    }
}
