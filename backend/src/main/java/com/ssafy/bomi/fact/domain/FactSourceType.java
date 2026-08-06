package com.ssafy.bomi.fact.domain;

/**
 * Origin of a {@link FactCandidate} (§6, §10).
 *
 * <p>{@code ONBOARDING_ANSWER} requires {@code onboarding_answer_id};
 * {@code CONVERSATION_MESSAGE} requires {@code conversation_id} and
 * {@code source_message_id}.</p>
 */
public enum FactSourceType {
    ONBOARDING_ANSWER,
    CONVERSATION_MESSAGE
}
