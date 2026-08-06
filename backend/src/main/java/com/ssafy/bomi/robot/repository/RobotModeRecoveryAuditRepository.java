package com.ssafy.bomi.robot.repository;

import com.ssafy.bomi.robot.domain.RobotModeRecoveryAudit;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RobotModeRecoveryAuditRepository
    extends JpaRepository<RobotModeRecoveryAudit, UUID> {
}
