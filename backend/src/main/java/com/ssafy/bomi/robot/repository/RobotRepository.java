package com.ssafy.bomi.robot.repository;

import com.ssafy.bomi.robot.domain.Robot;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RobotRepository extends JpaRepository<Robot, UUID> {
}
