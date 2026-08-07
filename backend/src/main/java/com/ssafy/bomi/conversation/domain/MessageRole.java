package com.ssafy.bomi.conversation.domain;

/**
 * Speaker role of a {@link ConversationMessage}.
 *
 * <p>Values follow the MVP ERD code dictionary (§10):
 * {@code SENIOR} (the senior) and {@code ROBOT} (the companion robot).</p>
 */
public enum MessageRole {
    SENIOR,
    ROBOT
}
