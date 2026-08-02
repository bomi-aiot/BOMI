package com.ssafy.bomi.care.web.dto;

/**
 * 복약 응답 DTO. 스케줄의 복용 시각을 펼치고 복용 기록(MEDICATION_TAKEN)과 매칭한 결과.
 * status(UPCOMING/MISSED/CONFIRMED/DECLINED)는 서버 계산값이며 FE 도 시각 기준으로 재파생한다.
 */
public record MedicationResponseDto(
        String id,
        String medicationId,
        String medicationScheduleId,
        String scheduledAt,
        String respondedAt,
        String status,
        String responseText) {
}
