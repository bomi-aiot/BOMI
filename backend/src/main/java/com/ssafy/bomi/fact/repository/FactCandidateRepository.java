package com.ssafy.bomi.fact.repository;

import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FactCandidateRepository extends JpaRepository<FactCandidate, UUID> {

    List<FactCandidate> findBySeniorIdAndStatusInOrderByCreatedAtDesc(
            UUID seniorId, Collection<FactCandidateStatus> statuses);

    long countBySeniorIdAndStatusIn(UUID seniorId, Collection<FactCandidateStatus> statuses);

    /**
     * Candidates the robot could raise in conversation, oldest first.
     *
     * <p>Oldest first so nothing starves. The caller then picks <b>exactly one</b> —
     * the ERD contract allows a single active candidate per conversation, and asking
     * about three pending facts at once breaks it (CLAUDE.md §12).</p>
     */
    List<FactCandidate> findBySeniorIdAndStatusInOrderByCreatedAtAsc(
            UUID seniorId, Collection<FactCandidateStatus> statuses);

    /**
     * The candidate produced by a given onboarding answer.
     *
     * <p>Answers are upserted, so their candidate is updated in place rather than
     * duplicated. Without this lookup, re-answering a question would leave the old
     * candidate behind and the senior would be asked about the same fact twice.</p>
     */
    Optional<FactCandidate> findByOnboardingAnswerId(UUID onboardingAnswerId);
}
