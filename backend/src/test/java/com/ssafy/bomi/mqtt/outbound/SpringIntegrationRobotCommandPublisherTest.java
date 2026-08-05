package com.ssafy.bomi.mqtt.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
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
        RobotCommand command = command();

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

    private static SpringIntegrationRobotCommandPublisher publisher(MessageChannel channel) {
        return new SpringIntegrationRobotCommandPublisher(
            channel, mapper(), new BomiMqttProperties());
    }

    private static ObjectMapper mapper() {
        return new ObjectMapper().registerModule(new JavaTimeModule());
    }

    private static RobotCommand command() {
        return new RobotCommand(
            "command-opaque-01",
            UUID.randomUUID(),
            "robot-01",
            RobotCommandType.NAVIGATE,
            OffsetDateTime.parse("2026-07-21T10:30:01+09:00"),
            OffsetDateTime.parse("2026-07-21T10:31:01+09:00"),
            Map.of("target", "ENTRANCE"));
    }
}
