package com.ssafy.bomi.fact.repository;

import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FactCandidateRepository extends JpaRepository<FactCandidate, UUID> {

    List<FactCandidate> findBySeniorIdAndStatusInOrderByCreatedAtDesc(
            UUID seniorId, Collection<FactCandidateStatus> statuses);

    long countBySeniorIdAndStatusIn(UUID seniorId, Collection<FactCandidateStatus> statuses);
}
