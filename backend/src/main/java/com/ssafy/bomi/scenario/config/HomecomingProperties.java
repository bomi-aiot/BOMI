package com.ssafy.bomi.scenario.config;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Homecoming scenario configuration (prefix {@code bomi.homecoming}).
 *
 * <p>MVP device mapping: door-sensor device ids on MQTT topics
 * (e.g. {@code "door-sensor-01"}) map to the senior (UUID) whose home they guard.
 * Robots resolve via their own {@code device_id} column, so only the sensor side
 * needs a config map until a sensor registry exists.</p>
 *
 * <p>Example:</p>
 * <pre>
 * bomi:
 *   homecoming:
 *     sensor-to-senior:
 *       door-sensor-01: 11111111-1111-1111-1111-111111111111
 * </pre>
 */
@Component
@ConfigurationProperties(prefix = "bomi.homecoming")
public class HomecomingProperties {

    private Map<String, UUID> sensorToSenior = new HashMap<>();

    public Map<String, UUID> getSensorToSenior() {
        return sensorToSenior;
    }

    public void setSensorToSenior(Map<String, UUID> sensorToSenior) {
        this.sensorToSenior = sensorToSenior == null ? new HashMap<>() : sensorToSenior;
    }

    /** Resolves the senior a door sensor belongs to, or throws if unmapped. */
    public UUID resolveSenior(String sensorId) {
        UUID seniorId = sensorToSenior.get(sensorId);
        if (seniorId == null) {
            throw new IllegalStateException("No senior mapped for door sensor: " + sensorId);
        }
        return seniorId;
    }
}
