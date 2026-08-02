package com.ssafy.bomi.care.web.dto;

import java.util.List;

/**
 * 복약(care_record: MEDICATION) 응답 DTO. 자식 care_record(MEDICATION_SCHEDULE)를 schedules 로 포함.
 * details 원본 필드명(medicationName/dose/doseUnit/instruction)을 그대로 내보내고,
 * FE 매퍼가 name/dosage 등으로 변환한다(계약퍼스트).
 */
public record MedicationDto(
        String id,
        String recordType,
        String status,
        String medicationName,
        String dose,
        String doseUnit,
        String instruction,
        String purpose,
        String activeIngredient,
        String startedOn,
        String endedOn,
        Boolean reminderEnabled,
        List<MedicationScheduleDto> schedules) {

    public record MedicationScheduleDto(
            String id,
            String medicationId,
            String recurrence,
            String timeZone,
            List<String> localTimes,
            Integer reminderLeadMinutes,
            boolean isActive) {
    }
}
