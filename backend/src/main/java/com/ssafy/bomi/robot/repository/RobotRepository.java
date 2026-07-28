package com.ssafy.bomi.robot.repository;

import com.ssafy.bomi.robot.domain.Robot;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RobotRepository extends JpaRepository<Robot, UUID> {

    /** Resolves a robot by its MQTT device identifier (e.g. {@code "robot-01"}). */
    Optional<Robot> findByDeviceId(String deviceId);

    /** Resolves the robot currently assigned to a senior. */
    Optional<Robot> findBySeniorId(UUID seniorId);
}
