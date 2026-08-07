package com.ssafy.bomi.onboarding.domain;

/**
 * Verification state of an {@link OnboardingAnswer}.
 *
 * <p>Values follow the {@code ONBOARDING_ANSWER_ENUM} code dictionary of the MVP
 * ERD. {@code UNVERIFIED} is the SQL default.</p>
 */
public enum AnswerVerificationStatus {
    UNVERIFIED,
    AUTO_ACCEPTED,
    USER_CONFIRMED,
    GUARDIAN_CONFIRMED,
    REJECTED
}
