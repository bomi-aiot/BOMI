package com.ssafy.bomi.care.web.dto;

/** 복약 등록/수정 요청 DTO 모음. FE Create/UpdateMedicationInput 과 대응. */
public final class MedicationRequests {

    private MedicationRequests() {
    }

    /** dosage 는 "1정" 같은 단일 문자열로 받는다(details.dose 에 그대로 저장, doseUnit 은 비움). */
    public record CreateMedicationRequest(
            String name,
            String dosage,
            String purpose,
            String instructions,
            String activeIngredient,
            String localTime,
            Boolean reminderEnabled,
            Integer reminderLeadMinutes) {
    }

    public record UpdateMedicationRequest(
            String name,
            String dosage,
            String purpose,
            String instructions,
            String activeIngredient,
            Boolean reminderEnabled,
            String verificationStatus,
            String localTime) {
    }
}
