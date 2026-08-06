package com.ssafy.bomi.fact.domain;

/**
 * The PRIMARY guardian's final decision on a {@link FactCandidate} (§7, §10).
 */
public enum PrimaryGuardianDecision {
    PENDING,
    CONFIRMED_EXISTING_VALUE,
    CONFIRMED_PROPOSED_VALUE,
    REVISED_VALUE,
    CANCELLED_CHANGE
}
