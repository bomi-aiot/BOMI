package com.ssafy.bomi.robot.repository;

import com.ssafy.bomi.robot.domain.Robot;
import jakarta.persistence.LockModeType;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface RobotRepository extends JpaRepository<Robot, UUID> {

    /** Resolves a robot by its MQTT device identifier (e.g. {@code "robot-01"}). */
    Optional<Robot> findByDeviceId(String deviceId);

    /** Serializes scenario starts addressed to the same physical Robot. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select r from Robot r where r.deviceId = :deviceId")
    Optional<Robot> findByDeviceIdForUpdate(@Param("deviceId") String deviceId);

    /** Serializes mode writers that already resolved the database Robot id. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select r from Robot r where r.id = :id")
    Optional<Robot> findByIdForUpdate(@Param("id") UUID id);

    /** Resolves the robot currently assigned to a senior. */
    Optional<Robot> findBySeniorId(UUID seniorId);
}
