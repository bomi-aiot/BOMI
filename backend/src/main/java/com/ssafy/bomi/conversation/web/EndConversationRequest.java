package com.ssafy.bomi.conversation.web;

import com.ssafy.bomi.conversation.domain.ConversationStatus;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

/**
 * The robot reporting that it has already decided a conversation is over
 * (S15P11E102-254).
 *
 * @param seniorId whose conversation this is. Checked against the conversation's own
 *     {@code senior_id} the same way {@code RecordTurnRequest.seniorId} is — a loud
 *     failure rather than a silent misdirection.
 * @param status the terminal status to apply: {@code COMPLETED} for a normal end,
 *     {@code FAILED} for an unanswered liveness probe (CLAUDE.md §10), {@code CANCELLED}
 *     for a conversation with nothing worth keeping. {@code OPEN} is rejected.
 * @param sealed {@code true} when the robot judged this conversation "우리끼리 얘기"
 *     and sealed it locally (S15P11E102-253, {@code emotion.is_conversation_sealed}).
 *     Sealing is one-directional: {@code null} or {@code false} does nothing, there is
 *     no way to unseal. A sealed conversation is never summarised (CLAUDE.md §9 T4).
 */
public record EndConversationRequest(
    @NotNull UUID seniorId,
    @NotNull ConversationStatus status,
    Boolean sealed) {
}
