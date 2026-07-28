package com.ssafy.bomi.fact.domain;

/**
 * Processing stage of a {@link FactCandidate} (§6, §10).
 *
 * <p>Distinct from {@code coordination_status} (the PRIMARY-coordination stage);
 * the two must not be conflated. Only a {@code confirmed_value} may be
 * materialized.</p>
 */
public enum FactCandidateStatus {
    CAPTURED,
    NEEDS_CLARIFICATION,
    NEEDS_CONFIRMATION,
    COORDINATION_REQUIRED,
    CONFIRMED,
    MATERIALIZED,
    REJECTED,
    EXPIRED
}
