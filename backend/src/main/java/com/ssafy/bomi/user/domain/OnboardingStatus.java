package com.ssafy.bomi.user.domain;

/**
 * Onboarding progress of an {@link AppUser}.
 *
 * <p>Values follow the {@code APP_USER_ENUM} code dictionary of the MVP ERD
 * ({@code onboarding_status}); {@code NOT_STARTED} is the SQL default.</p>
 */
public enum OnboardingStatus {
    NOT_STARTED,
    IN_PROGRESS,
    COMPLETED,
    DECLINED
}
