package com.ssafy.bomi.observation.config;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Robot-observation configuration (prefix {@code bomi.observation}).
 *
 * <p>Ambient-environment observations arrive as IoT events whose topic
 * {@code sourceId} is an environmental sensor device id. This map resolves that
 * sensor to the senior (UUID) whose home it monitors — the same style as the
 * door-sensor mapping. Robot-sourced observations (rest state) resolve via the
 * robot's own {@code device_id} and need no config here.</p>
 *
 * <pre>
 * bomi:
 *   observation:
 *     ambient-sensor-to-senior:
 *       ambient-sensor-01: 11111111-1111-1111-1111-111111111111
 * </pre>
 */
@Component
@ConfigurationProperties(prefix = "bomi.observation")
public class ObservationProperties {

    private Map<String, UUID> ambientSensorToSenior = new HashMap<>();

    public Map<String, UUID> getAmbientSensorToSenior() {
        return ambientSensorToSenior;
    }

    public void setAmbientSensorToSenior(Map<String, UUID> ambientSensorToSenior) {
        this.ambientSensorToSenior = ambientSensorToSenior == null ? new HashMap<>() : ambientSensorToSenior;
    }

    /** Resolves the senior an ambient sensor belongs to, or throws if unmapped. */
    public UUID resolveSenior(String sensorId) {
        UUID seniorId = ambientSensorToSenior.get(sensorId);
        if (seniorId == null) {
            throw new IllegalStateException("No senior mapped for ambient sensor: " + sensorId);
        }
        return seniorId;
    }
}
