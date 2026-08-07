package com.ssafy.bomi.fact.domain;

/**
 * The senior's recorded position during coordination of a {@link FactCandidate}
 * (§7, §10).
 */
public enum SeniorPosition {
    NOT_REQUESTED,
    PENDING,
    AGREED,
    DISAGREED,
    UNREACHABLE
}
