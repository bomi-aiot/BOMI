package com.ssafy.bomi.care.web.dto;

/**
 * 일정(care_record: APPOINTMENT/PERSONAL_SCHEDULE) 응답 DTO.
 * care_record.details(계약 §1-4)의 키를 그대로 미러링한다. 시각은 문자열(ISO).
 * 표시값 변환(status enum 등)은 FE 매퍼가 담당.
 */
public record ScheduleDto(
        String id,
        String recordType,
        String status,
        String title,
        String startsAt,
        String endsAt,
        String location,
        String relatedPersonName,
        String description,
        Boolean reminderEnabled,
        Integer reminderLeadMinutes,
        Boolean followUpEnabled,
        String followUpQuestion) {
}
