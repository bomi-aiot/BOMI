package com.ssafy.bomi.scenario.config;

import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
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

    /**
     * Resolves the senior a door sensor belongs to.
     *
     * <p>미등록 센서는 빈 값을 돌려준다. 예외를 던지면 인바운드 엔드포인트가 ack 를
     * 생략해 브로커가 같은 메시지를 무한 재전송하므로(QoS 1), 호출부는 경고 후
     * 폐기해야 한다 — 센서 id 오타 하나가 수신 파이프라인 전체를 막으면 안 된다.</p>
     */
    public Optional<UUID> findSenior(String sensorId) {
        return Optional.ofNullable(sensorToSenior.get(sensorId));
    }
}
