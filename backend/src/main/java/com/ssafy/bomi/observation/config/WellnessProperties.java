package com.ssafy.bomi.observation.config;

import java.math.BigDecimal;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 온습도 안부 확인(WELLNESS_CHECK) 판정 설정 (prefix {@code bomi.wellness}).
 *
 * <p>임계값 판단은 백엔드가 한다 — 센서는 측정값만 보낸다(계약 v1.0). 값은 시연
 * 연출(드라이기/가습기)로 유발 가능한 수준을 기본으로 하고 env 로 조정한다.</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.wellness")
public class WellnessProperties {

    /** 온습도 임계값 초과 시 독립 WELLNESS_CHECK 시나리오를 시작할지 여부. */
    private boolean scenarioEnabled = true;

    /** 이 온도(°C) 이상이면 이상으로 판정. */
    private BigDecimal temperatureThresholdC = new BigDecimal("30.0");

    /** 이 습도(%) 이상이면 이상으로 판정. */
    private BigDecimal humidityThresholdPercent = new BigDecimal("80.0");

    /** 같은 어르신에게 WELLNESS_CHECK 완료 후 재시작 금지 시간(분). */
    private long cooldownMinutes = 30;

    public boolean isScenarioEnabled() {
        return scenarioEnabled;
    }

    public void setScenarioEnabled(boolean scenarioEnabled) {
        this.scenarioEnabled = scenarioEnabled;
    }

    public BigDecimal getTemperatureThresholdC() {
        return temperatureThresholdC;
    }

    public void setTemperatureThresholdC(BigDecimal temperatureThresholdC) {
        this.temperatureThresholdC = temperatureThresholdC;
    }

    public BigDecimal getHumidityThresholdPercent() {
        return humidityThresholdPercent;
    }

    public void setHumidityThresholdPercent(BigDecimal humidityThresholdPercent) {
        this.humidityThresholdPercent = humidityThresholdPercent;
    }

    public long getCooldownMinutes() {
        return cooldownMinutes;
    }

    public void setCooldownMinutes(long cooldownMinutes) {
        this.cooldownMinutes = cooldownMinutes;
    }

    public Duration cooldown() {
        return Duration.ofMinutes(cooldownMinutes);
    }
}
