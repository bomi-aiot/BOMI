package com.ssafy.bomi.scenario.domain;

import com.ssafy.bomi.conversation.domain.ConversationIntent;
import java.util.Map;

/** Conversation input captured when a scenario starts and reused after navigation. */
public record PreparedConversation(
    ConversationIntent intent,
    String text,
    Map<String, Object> triggerContext
) {

    public PreparedConversation {
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
