package com.ssafy.bomi.occupancy.domain;

import com.ssafy.bomi.robot.domain.OccupancyStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;

/**
 * Raw ledger of entrance/occupancy changes (maps table {@code occupancy_event}).
 *
 * <p>Distinct from {@code scenario}, which records a <em>greeting run</em>. This
 * records the <em>fact</em>: the senior passed the door even if no greeting was
 * spoken because its TTL expired or the gate held it back.</p>
 *
 * <p>Three things read it: routine-baseline learning (the primary false-positive
 * filter for the silence ladder), outing-frequency trends for the T2 report, and
 * night-time wandering detection — which the silence ladder is structurally blind
 * to, because wandering is <em>activity</em>, not silence (CLAUDE.md §11).</p>
 *
 * <p>{@code senior_id} and {@code robot_id} are raw {@link UUID} logical
 * references; the SQL declares no foreign key, matching the entity convention.</p>
 */
@Entity
@Table(name = "occupancy_event")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class OccupancyEvent {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "robot_id")
    private UUID robotId;

    /**
     * Null when occupancy changed without anyone passing the door — a heartbeat
     * timeout or a speech-derived promotion. Check {@link #source} to tell which.
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "direction", length = 10)
    private OccupancyDirection direction;

    @Enumerated(EnumType.STRING)
    @Column(name = "source", nullable = false, length = 30)
    private OccupancyEventSource source;

    /**
     * Occupancy after applying this event. Storing the outcome alongside the cause
     * is what lets us reconstruct "what did we believe at the time", which is the
     * only way to debug a false escalation after the fact.
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "resulting_occupancy", nullable = false, length = 30)
    private OccupancyStatus resultingOccupancy;

    /**
     * When the event arrived at the Jetson. <strong>This is the authoritative
     * time.</strong>
     *
     * <p>A Raspberry Pi without a battery-backed RTC can boot with a wrong clock,
     * and a wrong door timestamp corrupts both the routine baseline and TTL
     * arithmetic. So the Pi's own timestamp is advisory only
     * ({@link #reportedAt}) and this value is normalized on arrival.</p>
     */
    @Column(name = "occurred_at", nullable = false)
    private OffsetDateTime occurredAt;

    /** The entrance node's own timestamp. Advisory — never used for arithmetic. */
    @Column(name = "reported_at")
    private OffsetDateTime reportedAt;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    private OccupancyEvent(UUID seniorId, UUID robotId, OccupancyDirection direction,
        OccupancyEventSource source, OccupancyStatus resultingOccupancy, OffsetDateTime occurredAt,
        OffsetDateTime reportedAt) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.source = requireNonNull(source, "source");
        this.resultingOccupancy = requireNonNull(resultingOccupancy, "resultingOccupancy");
        this.occurredAt = requireNonNull(occurredAt, "occurredAt");
        this.robotId = robotId;
        this.direction = direction;
        this.reportedAt = reportedAt;
    }

    /**
     * A confirmed passage through the entrance.
     *
     * @param occurredAt arrival time at the Jetson, not the Pi's clock
     * @param reportedAt the Pi's own timestamp, may be {@code null}
     */
    public static OccupancyEvent passage(UUID seniorId, UUID robotId, OccupancyDirection direction,
        OccupancyStatus resultingOccupancy, OffsetDateTime occurredAt, OffsetDateTime reportedAt) {
        return new OccupancyEvent(seniorId, robotId, requireNonNull(direction, "direction"),
            OccupancyEventSource.DOOR_SENSOR, resultingOccupancy, occurredAt, reportedAt);
    }

    /**
     * Speech promoted occupancy to {@code HOME}. No direction: nobody passed the
     * door, we simply learned they are here.
     */
    public static OccupancyEvent fromSpeech(UUID seniorId, UUID robotId, OffsetDateTime occurredAt) {
        return new OccupancyEvent(seniorId, robotId, null, OccupancyEventSource.SPEECH,
            OccupancyStatus.HOME, occurredAt, null);
    }

    /**
     * The entrance node went silent, so occupancy degraded to {@code UNKNOWN}.
     * Recording this is what separates "nobody moved" from "the sensor died".
     */
    public static OccupancyEvent heartbeatLost(UUID seniorId, UUID robotId, OffsetDateTime occurredAt) {
        return new OccupancyEvent(seniorId, robotId, null, OccupancyEventSource.HEARTBEAT_TIMEOUT,
            OccupancyStatus.UNKNOWN, occurredAt, null);
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
