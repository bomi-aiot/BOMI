package com.ssafy.bomi.conversation.domain;

/**
 * Type of a {@link ConversationSummary}.
 *
 * <p>The MVP uses only {@code CONVERSATION} (one conversation) and {@code DAILY}
 * (one local calendar day). {@code TIME_WINDOW} is intentionally deferred until
 * a real long-conversation problem is observed (§4, §12).</p>
 */
public enum SummaryType {
    CONVERSATION,
    DAILY
}
