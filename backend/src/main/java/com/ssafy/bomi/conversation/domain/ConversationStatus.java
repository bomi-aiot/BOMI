package com.ssafy.bomi.conversation.domain;

/**
 * Lifecycle status of a {@link Conversation}.
 *
 * <p>Values follow the MVP ERD code dictionary (§10):
 * {@code OPEN}, {@code COMPLETED}, {@code FAILED}, {@code CANCELLED}.
 * {@code OPEN} is the working default (the finalized ERD supersedes the older
 * {@code ACTIVE} default seen in the draft SQL export).</p>
 */
public enum ConversationStatus {
    OPEN,
    COMPLETED,
    FAILED,
    CANCELLED
}
