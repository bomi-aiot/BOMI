package com.ssafy.bomi.robot.repository;

import com.ssafy.bomi.robot.domain.OccupancyStatus;
import com.ssafy.bomi.robot.domain.Robot;
import jakarta.persistence.LockModeType;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface RobotRepository extends JpaRepository<Robot, UUID> {

    /** Lightweight non-locking identity used before acquiring the shared senior mutex. */
    interface LockCandidate {
        UUID getId();

        UUID getSeniorId();
    }

    /** Resolves a robot by its MQTT device identifier (e.g. {@code "robot-01"}). */
    Optional<Robot> findByDeviceId(String deviceId);

    /**
     * Resolves only the keys needed to establish the senior-then-robot lock order.
     * Returning a projection avoids attaching a stale Robot entity before the lock query.
     */
    @Query("select r.id as id, r.seniorId as seniorId from Robot r where r.deviceId = :deviceId")
    Optional<LockCandidate> findLockCandidateByDeviceId(@Param("deviceId") String deviceId);

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

    /** Locks the Robot assigned to a senior after the shared senior-row mutex is held. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select r from Robot r where r.seniorId = :seniorId")
    Optional<Robot> findBySeniorIdForUpdate(@Param("seniorId") UUID seniorId);

    /** Resolves one authoritative Robot id without attaching a stale Robot snapshot. */
    @Query("select r.id from Robot r where r.seniorId = :seniorId")
    Optional<UUID> findIdBySeniorId(@Param("seniorId") UUID seniorId);

    /**
     * Updates only the ambient snapshot columns.
     *
     * <p>A sensor observation must never write a stale {@code current_mode} back over a
     * concurrently committed scenario or SAFE_STOP transition.</p>
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Robot r
           set r.ambientTemperatureC = :temperatureC,
               r.ambientHumidityPercent = :humidityPercent,
               r.ambientObservedAt = :observedAt
         where r.id = :robotId
        """)
    int updateAmbientSnapshotById(
        @Param("robotId") UUID robotId,
        @Param("temperatureC") BigDecimal temperatureC,
        @Param("humidityPercent") BigDecimal humidityPercent,
        @Param("observedAt") OffsetDateTime observedAt
    );

    /** Updates only occupancy snapshot columns, preserving concurrent mode changes. */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Robot r
           set r.occupancyStatus = :status,
               r.occupancyObservedAt = :observedAt
         where r.id = :robotId
        """)
    int updateOccupancySnapshotById(
        @Param("robotId") UUID robotId,
        @Param("status") OccupancyStatus status,
        @Param("observedAt") OffsetDateTime observedAt
    );
}
