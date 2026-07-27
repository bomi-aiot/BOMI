package com.ssafy.bomi.fact.repository;

import com.ssafy.bomi.fact.domain.FactCandidate;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FactCandidateRepository extends JpaRepository<FactCandidate, UUID> {
}
