package com.ssafy.bomi.user.domain;

/**
 * Consent state shared by the personalization, health-data, schedule and
 * guardian-sharing consent columns of {@link AppUser}.
 *
 * <p>Only {@code NOT_REQUESTED} is confirmed by the SQL default; the remaining
 * values are provisional and must be reconciled with the finalized ERD.</p>
 */
public enum ConsentStatus {
    NOT_REQUESTED,
    GRANTED,
    DENIED
}
