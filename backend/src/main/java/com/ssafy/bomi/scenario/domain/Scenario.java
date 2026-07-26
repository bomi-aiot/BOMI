package com.ssafy.bomi.scenario.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * Scenario triggered for a senior/robot (maps table {@code scenario}).
 *
 * <p>Aggregate root. Although {@code conversation} references {@code scenario},
 * this entity is independent and deliberately holds <b>no</b> back-reference to
 * conversations. {@code scenario_type} and {@code final_status} are raw
 * {@link String}s because the SQL enumerates no allowed values (final_status even
 * defaults to an empty string).</p>
 */
@Entity
@Table(name = "scenario")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Scenario {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "robot_id", nullable = false)
    private UUID robotId;

    @Column(name = "external_event_id", length = 255)
    private String externalEventId;

    @Column(name = "scenario_type", nullable = false, length = 50)
    private String scenarioType;

    @Column(name = "final_status", nullable = false, length = 255)
    private String finalStatus = "";

    private Scenario(UUID seniorId, UUID robotId, String scenarioType, String externalEventId) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.robotId = requireNonNull(robotId, "robotId");
        this.scenarioType = requireText(scenarioType, "scenarioType");
        this.externalEventId = externalEventId;
    }

    public static Scenario create(UUID seniorId, UUID robotId, String scenarioType) {
        return new Scenario(seniorId, robotId, scenarioType, null);
    }

    public static Scenario create(UUID seniorId, UUID robotId, String scenarioType, String externalEventId) {
        return new Scenario(seniorId, robotId, scenarioType, externalEventId);
    }

    public void linkExternalEvent(String externalEventId) {
        this.externalEventId = externalEventId;
    }

    public void updateFinalStatus(String finalStatus) {
        this.finalStatus = finalStatus == null ? "" : finalStatus;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
