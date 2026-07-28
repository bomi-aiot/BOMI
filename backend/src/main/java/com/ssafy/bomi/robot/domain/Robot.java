package com.ssafy.bomi.robot.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Companion robot device (maps table {@code robot}).
 *
 * <p>Aggregate root. {@code senior_id} is a nullable logical reference to
 * {@code app_user} and is stored as a raw {@link UUID}; the SQL declares no
 * foreign key so no object association is created.</p>
 */
@Entity
@Table(name = "robot")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Robot {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id")
    private UUID seniorId;

    /**
     * Stable device identifier used on MQTT topics (e.g. {@code "robot-01"}), used
     * to resolve this robot from inbound messages and to address outbound commands.
     * Nullable so pre-existing rows / test fixtures without a device stay valid.
     */
    @Column(name = "device_id", unique = true, length = 64)
    private String deviceId;

    @Enumerated(EnumType.STRING)
    @Column(name = "current_mode", nullable = false, length = 30)
    private RobotMode currentMode = RobotMode.IDLE;

    @Column(name = "ambient_temperature_c", precision = 5, scale = 2)
    private BigDecimal ambientTemperatureC;

    @Column(name = "ambient_humidity_percent", precision = 5, scale = 2)
    private BigDecimal ambientHumidityPercent;

    @Column(name = "ambient_observed_at")
    private OffsetDateTime ambientObservedAt;

    @Column(name = "is_active", nullable = false)
    private boolean active = true;

    private Robot(UUID seniorId) {
        this.seniorId = seniorId;
    }

    /** Creates a robot, optionally already assigned to a senior (may be {@code null}). */
    public static Robot create(UUID seniorId) {
        return new Robot(seniorId);
    }

    /** Creates a robot with its MQTT device identifier already registered. */
    public static Robot create(UUID seniorId, String deviceId) {
        Robot robot = new Robot(seniorId);
        robot.registerDevice(deviceId);
        return robot;
    }

    /** Registers/updates the MQTT device identifier for this robot. */
    public void registerDevice(String deviceId) {
        if (deviceId == null || deviceId.isBlank()) {
            throw new IllegalArgumentException("deviceId must not be blank");
        }
        this.deviceId = deviceId;
    }

    public void assignSenior(UUID seniorId) {
        if (seniorId == null) {
            throw new IllegalArgumentException("seniorId must not be null");
        }
        this.seniorId = seniorId;
    }

    public void unassignSenior() {
        this.seniorId = null;
    }

    public void changeMode(RobotMode mode) {
        if (mode == null) {
            throw new IllegalArgumentException("mode must not be null");
        }
        this.currentMode = mode;
    }

    public void activate() {
        this.active = true;
    }

    public void deactivate() {
        this.active = false;
    }

    /** Records the latest ambient reading reported by the device. */
    public void recordAmbient(BigDecimal temperatureC, BigDecimal humidityPercent, OffsetDateTime observedAt) {
        this.ambientTemperatureC = temperatureC;
        this.ambientHumidityPercent = humidityPercent;
        this.ambientObservedAt = observedAt;
    }
}
