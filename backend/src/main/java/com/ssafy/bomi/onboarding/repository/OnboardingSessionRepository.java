package com.ssafy.bomi.onboarding.repository;

import com.ssafy.bomi.onboarding.domain.OnboardingSession;
import com.ssafy.bomi.onboarding.domain.OnboardingSessionStatus;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OnboardingSessionRepository extends JpaRepository<OnboardingSession, UUID> {

    /**
     * The senior's in-progress session, if any.
     *
     * <p>A senior has at most one in-progress session (onboarding design note §2). This
     * lookup is what makes "started in the app, finished by voice" work: the robot
     * resumes the existing row instead of opening a second one, so
     * {@code started_channel} stays APP and only {@code answered_channel} says ROBOT.</p>
     *
     * <p>Ordered defensively. The invariant says there is one, but if a bug ever produced
     * two, silently picking an arbitrary row would hide it — taking the newest at least
     * keeps behaviour predictable while the duplicate is investigated.</p>
     */
    Optional<OnboardingSession> findFirstBySeniorIdAndStatusOrderByStartedAtDesc(
        UUID seniorId, OnboardingSessionStatus status);
}
