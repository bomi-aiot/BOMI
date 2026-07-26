package com.ssafy.bomi.onboarding.repository;

import com.ssafy.bomi.onboarding.domain.OnboardingSession;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OnboardingSessionRepository extends JpaRepository<OnboardingSession, UUID> {
}
