package com.ssafy.bomi.mqtt.outbound;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.conversation.domain.ConversationIntent;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AiConversationCommandTest {

    @Test
    void keepsRequiredCorrelationAndCopiesTriggerContext() {
        Map<String, Object> context = new HashMap<>();
        context.put("location", "ENTRANCE");
        StartConversationPayload payload = new StartConversationPayload(
            UUID.randomUUID(), ConversationIntent.HOMECOMING_GREETING, "어서 오세요.", context);
        OffsetDateTime occurredAt = OffsetDateTime.parse("2026-08-05T10:00:00+09:00");
        AiConversationCommand command = new AiConversationCommand(
            "cmd-ai-01", UUID.randomUUID(), UUID.randomUUID(), "robot-01",
            AiConversationCommandType.START_CONVERSATION,
            occurredAt, occurredAt.plusSeconds(10), payload);
        context.put("location", "MUTATED");

        assertThat(command.payload().triggerContext()).containsEntry("location", "ENTRANCE");
        assertThat(command.conversationId()).isNotNull();
    }

    @Test
    void rejectsBlankTextAndExpiredCommand() {
        assertThatThrownBy(() -> new StartConversationPayload(
            UUID.randomUUID(), ConversationIntent.HOMECOMING_GREETING, " ", Map.of()))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("text");

        OffsetDateTime occurredAt = OffsetDateTime.parse("2026-08-05T10:00:00+09:00");
        assertThatThrownBy(() -> new AiConversationCommand(
            "cmd-ai-01", UUID.randomUUID(), UUID.randomUUID(), "robot-01",
            AiConversationCommandType.START_CONVERSATION, occurredAt, occurredAt,
            new StartConversationPayload(
                UUID.randomUUID(), ConversationIntent.HOMECOMING_GREETING,
                "어서 오세요.", Map.of())))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("expiresAt");
    }
}
