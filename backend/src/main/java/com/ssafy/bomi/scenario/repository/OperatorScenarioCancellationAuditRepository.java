package com.ssafy.bomi.scenario.repository;

import com.ssafy.bomi.scenario.domain.OperatorScenarioCancellationAudit;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OperatorScenarioCancellationAuditRepository
    extends JpaRepository<OperatorScenarioCancellationAudit, UUID> {
}
