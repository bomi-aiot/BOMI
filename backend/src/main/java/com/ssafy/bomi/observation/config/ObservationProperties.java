package com.ssafy.bomi.observation.config;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
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

    /**
     * Resolves the senior an ambient sensor belongs to.
     *
     * <p>미등록 센서는 빈 값을 돌려준다. 예외를 던지면 인바운드 엔드포인트가 ack 를
     * 생략해 브로커가 같은 메시지를 무한 재전송하므로(QoS 1), 호출부는 경고 후
     * 폐기해야 한다 — 센서 id 오타 하나가 수신 파이프라인 전체를 막으면 안 된다.</p>
     */
    public Optional<UUID> findSenior(String sensorId) {
        return Optional.ofNullable(ambientSensorToSenior.get(sensorId));
    }
}
