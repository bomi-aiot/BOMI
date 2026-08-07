package com.ssafy.bomi.mqtt.outbound;

import com.ssafy.bomi.conversation.domain.ConversationIntent;
import java.util.Map;
import java.util.UUID;

/** Type-specific payload of START_CONVERSATION. */
public record StartConversationPayload(
    UUID seniorId,
    ConversationIntent intent,
    String text,
    Map<String, Object> triggerContext
) {

    public StartConversationPayload {
        if (seniorId == null) {
            throw new IllegalArgumentException("seniorId must not be null");
        }
        if (intent == null) {
            throw new IllegalArgumentException("intent must not be null");
        }
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException("text must not be blank");
        }
        if (text.length() > 500) {
            throw new IllegalArgumentException("text must not exceed 500 characters");
        }
        triggerContext = triggerContext == null ? Map.of() : Map.copyOf(triggerContext);
    }
}
