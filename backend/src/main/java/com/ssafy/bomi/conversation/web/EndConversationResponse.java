package com.ssafy.bomi.conversation.web;

import java.time.OffsetDateTime;
import java.util.UUID;

/** The conversation's state right after {@code end()} was applied. */
public record EndConversationResponse(
    UUID conversationId,
    String status,
    OffsetDateTime endedAt,
    OffsetDateTime rawMessagesExpiresAt) {
}
