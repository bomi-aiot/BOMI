package com.ssafy.bomi.scenario.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * 복약 알림(MEDICATION_REMINDER) 설정 (prefix {@code bomi.medication-reminder}).
 *
 * <p>알림 창 = [예정 시각 - reminderLeadMinutes(기록별), 예정 시각 + graceMinutes(공통)].
 * 창이 닫힌 슬롯은 조용히 지나간다 — 한참 지난 약을 뒤늦게 알리는 것은 알림이 아니라
 * 혼란이다. 놓친 복약의 추적은 알림이 아닌 복약 확인(MEDICATION_TAKEN) 축의 일이다.</p>
 */
@Component
@ConfigurationProperties(prefix = "bomi.medication-reminder")
public class MedicationReminderProperties {

    /** 예정 시각 이후 이 시간(분)까지는 아직 알릴 가치가 있다고 본다. */
    private long graceMinutes = 15;

    public long getGraceMinutes() {
        return graceMinutes;
    }

    public void setGraceMinutes(long graceMinutes) {
        this.graceMinutes = graceMinutes;
    }
}
