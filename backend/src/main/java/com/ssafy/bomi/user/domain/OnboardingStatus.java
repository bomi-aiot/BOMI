package com.ssafy.bomi.user.domain;

/**
 * Onboarding progress of an {@link AppUser}.
 *
 * <p>Only {@code NOT_STARTED} is confirmed by the SQL default; the remaining
 * values are provisional and must be reconciled with the finalized ERD.</p>
 */
public enum OnboardingStatus {
    NOT_STARTED,
    IN_PROGRESS,
    COMPLETED
}
