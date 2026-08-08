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
import com.ssafy.bomi.conversation.domain.ConversationIntent;
import com.ssafy.bomi.mqtt.config.BomiMqttProperties;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.transaction.support.TransactionSynchronizationManager;

class SpringIntegrationAiConversationCommandPublisherTest {

    @Test
    void publishesOnlyAfterActiveTransactionCommits() {
        MessageChannel channel = mock(MessageChannel.class);
        when(channel.send(any(Message.class), eq(5_000L))).thenReturn(true);
        SpringIntegrationAiConversationCommandPublisher publisher = publisher(channel);

        TransactionSynchronizationManager.initSynchronization();
        TransactionSynchronizationManager.setActualTransactionActive(true);
        try {
            publisher.publish(command());
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
    void publishesContractJsonToAiTopicWithoutTransaction() throws Exception {
        MessageChannel channel = mock(MessageChannel.class);
        when(channel.send(any(Message.class), eq(5_000L))).thenReturn(true);
        ObjectMapper objectMapper = mapper();
        SpringIntegrationAiConversationCommandPublisher publisher =
            new SpringIntegrationAiConversationCommandPublisher(
                channel, objectMapper, new BomiMqttProperties());

        publisher.publish(command());

        @SuppressWarnings("rawtypes")
        var captor = org.mockito.ArgumentCaptor.forClass(Message.class);
        verify(channel).send(captor.capture(), eq(5_000L));
        var json = objectMapper.readTree((String) captor.getValue().getPayload());
        assertThat(json.path("type").asText()).isEqualTo("START_CONVERSATION");
        assertThat(json.path("payload").path("intent").asText())
            .isEqualTo("HOMECOMING_GREETING");
    }

    private static SpringIntegrationAiConversationCommandPublisher publisher(
        MessageChannel channel
    ) {
        return new SpringIntegrationAiConversationCommandPublisher(
            channel, mapper(), new BomiMqttProperties());
    }

    private static ObjectMapper mapper() {
        return new ObjectMapper().registerModule(new JavaTimeModule());
    }

    private static AiConversationCommand command() {
        OffsetDateTime occurredAt = OffsetDateTime.parse("2026-08-05T10:00:00+09:00");
        return new AiConversationCommand(
            "cmd-ai-01", UUID.randomUUID(), UUID.randomUUID(), "robot-01",
            AiConversationCommandType.START_CONVERSATION,
            occurredAt, occurredAt.plusSeconds(10),
            new StartConversationPayload(
                UUID.randomUUID(),
                ConversationIntent.HOMECOMING_GREETING,
                "다녀오셨어요? 오늘 외출은 어떠셨어요?",
                Map.of("location", "ENTRANCE")));
    }
}
