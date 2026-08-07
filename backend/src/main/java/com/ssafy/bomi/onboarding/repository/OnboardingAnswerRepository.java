package com.ssafy.bomi.onboarding.repository;

import com.ssafy.bomi.onboarding.domain.OnboardingAnswer;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OnboardingAnswerRepository extends JpaRepository<OnboardingAnswer, UUID> {

    /**
     * The current answer to one question of one session.
     *
     * <p>Answers are upserted, not appended (onboarding design note §1). Re-asking a
     * field must overwrite the previous attempt — if both rows survived, "which value is
     * current" would depend on read order.</p>
     */
    Optional<OnboardingAnswer> findBySessionIdAndQuestionCode(UUID sessionId, String questionCode);

    List<OnboardingAnswer> findBySessionId(UUID sessionId);
}
