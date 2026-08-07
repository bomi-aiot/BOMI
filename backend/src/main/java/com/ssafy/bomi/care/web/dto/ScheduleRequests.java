package com.ssafy.bomi.care.web.dto;

/** 일정 등록/수정 요청 DTO 모음. FE Create/UpdateScheduleInput 과 대응. */
public final class ScheduleRequests {

    private ScheduleRequests() {
    }

    public record CreateScheduleRequest(
            String recordType,
            String title,
            String startsAt,
            String description,
            String endsAt,
            String location,
            String relatedPersonName,
            Boolean reminderEnabled,
            Integer reminderLeadMinutes,
            Boolean followUpEnabled,
            String followUpQuestion,
            String sourceType,
            String verificationStatus) {
    }

    public record UpdateScheduleRequest(
            String recordType,
            String title,
            String description,
            String startsAt,
            String endsAt,
            String location,
            String relatedPersonName,
            String status,
            Boolean reminderEnabled,
            Integer reminderLeadMinutes,
            Boolean followUpEnabled,
            String followUpQuestion,
            String verificationStatus) {
    }
}
