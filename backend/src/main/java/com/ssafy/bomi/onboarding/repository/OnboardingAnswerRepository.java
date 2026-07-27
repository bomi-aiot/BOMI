package com.ssafy.bomi.onboarding.repository;

import com.ssafy.bomi.onboarding.domain.OnboardingAnswer;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OnboardingAnswerRepository extends JpaRepository<OnboardingAnswer, UUID> {
}
