package com.ssafy.bomi.mqtt.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
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
import org.springframework.transaction.support.TransactionSynchronizationManager;

class SpringIntegrationRobotCommandPublisherTest {

    @Test
    void publishesOnlyAfterActiveTransactionCommits() {
        MessageChannel channel = mock(MessageChannel.class);
        when(channel.send(any(Message.class), eq(5_000L))).thenReturn(true);
        SpringIntegrationRobotCommandPublisher publisher = publisher(channel);
        RobotCommand command = command(
            RobotCommandType.FOLLOW_START,
            "command-follow-start",
            UUID.randomUUID());

        TransactionSynchronizationManager.initSynchronization();
        TransactionSynchronizationManager.setActualTransactionActive(true);
        try {
            publisher.publish(command);
            verifyNoInteractions(channel);

            TransactionSynchronizationManager.getSynchronizations()
                .forEach(synchronization -> synchronization.afterCommit());
            verify(channel).send(any(Message.class), eq(5_000L));
        } finally {
            TransactionSynchronizationManager.clearSynchronization();
            TransactionSynchronizationManager.setActualTransactionActive(false);
        }
    }

    @Test
    void publishesJsonToRobotCommandTopicWithContractHeadersWithoutTransaction() throws Exception {
        MessageChannel channel = mock(MessageChannel.class);
        when(channel.send(any(Message.class), eq(5_000L))).thenReturn(true);
        ObjectMapper objectMapper = mapper();
        SpringIntegrationRobotCommandPublisher publisher =
            new SpringIntegrationRobotCommandPublisher(
                channel, objectMapper, new BomiMqttProperties());

        publisher.publish(command());

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Message> captor = ArgumentCaptor.forClass(Message.class);
        verify(channel).send(captor.capture(), eq(5_000L));
        Message<?> message = captor.getValue();
        assertThat(message.getHeaders().get(MqttHeaders.TOPIC))
            .isEqualTo("bomi/v1/robot/robot-01/commands");
        assertThat(objectMapper.readTree((String) message.getPayload()).path("commandId").asText())
            .isEqualTo("command-opaque-01");
    }

    @Test
    void publishesBothFollowCommandsWithEmptyPayloadQosOneAndRetainFalse() throws Exception {
        MessageChannel channel = mock(MessageChannel.class);
        when(channel.send(any(Message.class), eq(5_000L))).thenReturn(true);
        ObjectMapper objectMapper = mapper();
        SpringIntegrationRobotCommandPublisher publisher =
            new SpringIntegrationRobotCommandPublisher(
                channel, objectMapper, new BomiMqttProperties());
        UUID scenarioId = UUID.randomUUID();

        publisher.publish(command(
            RobotCommandType.FOLLOW_START, "command-follow-start", scenarioId));
        publisher.publish(command(
            RobotCommandType.FOLLOW_STOP, "command-follow-stop", scenarioId));

        @SuppressWarnings("rawtypes")
        ArgumentCaptor<Message> captor = ArgumentCaptor.forClass(Message.class);
        verify(channel, times(2)).send(captor.capture(), eq(5_000L));
        assertThat(captor.getAllValues()).hasSize(2);

        for (int index = 0; index < 2; index++) {
            Message<?> message = captor.getAllValues().get(index);
            RobotCommandType expectedType = index == 0
                ? RobotCommandType.FOLLOW_START : RobotCommandType.FOLLOW_STOP;
            String expectedCommandId = index == 0
                ? "command-follow-start" : "command-follow-stop";

            assertThat(message.getHeaders().get(MqttHeaders.TOPIC))
                .isEqualTo("bomi/v1/robot/robot-01/commands");
            assertThat(message.getHeaders().get(MqttHeaders.QOS)).isEqualTo(1);
            assertThat(message.getHeaders().get(MqttHeaders.RETAINED)).isEqualTo(false);

            var json = objectMapper.readTree((String) message.getPayload());
            assertThat(json.path("commandId").asText()).isEqualTo(expectedCommandId);
            assertThat(json.path("scenarioId").asText()).isEqualTo(scenarioId.toString());
            assertThat(json.path("type").asText()).isEqualTo(expectedType.name());
            assertThat(json.path("payload").isObject()).isTrue();
            assertThat(json.path("payload").size()).isZero();
        }
    }

    private static SpringIntegrationRobotCommandPublisher publisher(MessageChannel channel) {
        return new SpringIntegrationRobotCommandPublisher(
            channel, mapper(), new BomiMqttProperties());
    }

    private static ObjectMapper mapper() {
        return new ObjectMapper().registerModule(new JavaTimeModule());
    }

    private static RobotCommand command() {
        return command(
            RobotCommandType.NAVIGATE,
            "command-opaque-01",
            UUID.randomUUID());
    }

    private static RobotCommand command(
        RobotCommandType type,
        String commandId,
        UUID scenarioId
    ) {
        return new RobotCommand(
            commandId,
            scenarioId,
            "robot-01",
            type,
            OffsetDateTime.parse("2026-07-21T10:30:01+09:00"),
            OffsetDateTime.parse("2026-07-21T10:31:01+09:00"),
            type == RobotCommandType.NAVIGATE
                ? Map.of("target", "ENTRANCE") : Map.of());
    }
}
