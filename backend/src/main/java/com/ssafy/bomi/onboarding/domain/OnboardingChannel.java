package com.ssafy.bomi.onboarding.domain;

/**
 * Channel through which onboarding is started or answered.
 *
 * <p>Shared by {@code onboarding_session.started_channel} and
 * {@code onboarding_answer.answered_channel} per the MVP ERD code dictionary
 * (§10). {@code started_channel} is the first channel; {@code answered_channel}
 * is the channel that actually produced a given answer.</p>
 */
public enum OnboardingChannel {
    APP,
    ROBOT
}
