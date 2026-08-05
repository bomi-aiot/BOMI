package com.ssafy.bomi.scenario.application;

import java.util.UUID;

/** Result of storing and publishing one START_CONVERSATION command. */
public record ConversationStartResult(
    UUID conversationId,
    boolean published,
    String failureReasonCode
) {

    public static ConversationStartResult published(UUID conversationId) {
        return new ConversationStartResult(conversationId, true, null);
    }

    public static ConversationStartResult failed(UUID conversationId, String reasonCode) {
        if (reasonCode == null || reasonCode.isBlank()) {
            throw new IllegalArgumentException("reasonCode must not be blank");
        }
        return new ConversationStartResult(conversationId, false, reasonCode);
    }
}
