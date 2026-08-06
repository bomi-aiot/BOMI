package com.ssafy.bomi.fact.domain;

/**
 * Reason the senior could not be reached during coordination of a
 * {@link FactCandidate} (§7, §10).
 */
public enum UnreachableReason {
    NO_RESPONSE,
    PHONE_UNAVAILABLE,
    TEMPORARY_HEALTH_CONDITION,
    COMMUNICATION_DIFFICULTY,
    OTHER
}
