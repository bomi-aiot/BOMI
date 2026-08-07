package com.ssafy.bomi.context.api;

import jakarta.validation.constraints.Positive;
import java.util.UUID;

/**
 * What the robot asks for when it needs context for one turn.
 *
 * <p>Sent as a request body rather than query parameters because {@code query} is the
 * senior's own utterance. Personal and health-related speech must not end up in URLs,
 * where it would be copied into access logs, proxies, and metrics by default.</p>
 *
 * @param query the current utterance, or a proposal's seed for a proactive turn. Used
 *     to judge which memories, summaries, and care records are relevant. May be blank
 *     for a turn with no text yet, in which case relevance falls back to recency.
 * @param conversationId the conversation whose raw tail to include. {@code null} on the
 *     first turn of a new conversation, which simply yields no recent messages.
 * @param memoryTopK how many long-term memories to return. Clamped to the configured
 *     3–10 range. The robot lowers this itself under pressure — that is the first step
 *     of its degradation order, not an error (CLAUDE.md §18).
 * @param recentMessageLimit size of the raw-message window, clamped to 6–12.
 * @param includeDocuments whether to search the reference corpus. The robot sets this
 *     only for the {@code info} intent; searching documents during small talk spends
 *     latency the two-second budget does not have and pollutes the prompt.
 * @param requesterGuardianId set when a guardian is the one asking, which narrows the
 *     visible memories. {@code null} means the robot is assembling context to talk to
 *     the senior, so {@code PRIVATE} memories are usable.
 */
public record ConversationContextRequest(
    String query,
    UUID conversationId,
    @Positive Integer memoryTopK,
    @Positive Integer recentMessageLimit,
    Boolean includeDocuments,
    UUID requesterGuardianId
) {

    /** Whether the caller asked for document retrieval. Defaults to no. */
    public boolean wantsDocuments() {
        return Boolean.TRUE.equals(includeDocuments);
    }

    /** The query text, never {@code null}, so callers need not null-check. */
    public String queryOrEmpty() {
        return query == null ? "" : query;
    }
}
