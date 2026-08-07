package com.ssafy.bomi.onboarding.domain;

/**
 * Lifecycle status of an {@link OnboardingSession}.
 *
 * <p>Values follow the {@code ONBOARDING_SESSION_ENUM} code dictionary of the
 * MVP ERD (§10). {@code IN_PROGRESS} is the working default. Reaching
 * {@code COMPLETED} requires the required-question / consent gates described in
 * §5.</p>
 */
public enum OnboardingSessionStatus {
    IN_PROGRESS,
    COMPLETED,
    DECLINED,
    CANCELLED,
    EXPIRED
}
