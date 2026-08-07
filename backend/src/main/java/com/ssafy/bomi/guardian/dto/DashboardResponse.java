package com.ssafy.bomi.guardian.dto;

import com.ssafy.bomi.fact.web.FactCandidateDto;
import java.math.BigDecimal;
import java.util.List;

/**
 * GET /v1/guardian/dashboard 응답. FE {@code HomeDashboardSummary}(camelCase) 모양과 맞춘다.
 * {@code confirmationRequests} 는 fact_candidate 원본 DTO 로 내보내며, FE 가 표시값으로 매핑한다.
 *
 * <p>P0 범위: {@code medications} 목록은 별도(복약 관리) 엔드포인트가 담당하므로 대시보드에서는 생략.
 * 대시보드 복약 카드는 {@code medicationResponses} 로 렌더한다.</p>
 */
public record DashboardResponse(
        ElderDto elder,
        RobotDto robot,
        HomeEnvironmentDto homeEnvironment,
        int todayIncidentCount,
        List<ScheduleDto> todaySchedules,
        List<MedicationResponseDto> medicationResponses,
        MedicationProgressDto medicationProgress,
        long pendingConfirmationCount,
        List<FactCandidateDto> confirmationRequests,
        List<ActivityDto> recentActivities,
        String generatedAt) {

    public record ElderDto(
            String id,
            String displayName,
            String statusLevel,
            String statusLabel,
            String lastCheckedAt) {
    }

    public record RobotDto(
            String id,
            String elderId,
            String deviceId,
            String currentMode,
            boolean isActive,
            BigDecimal ambientTemperatureC,
            BigDecimal ambientHumidityPercent,
            String ambientObservedAt) {
    }

    public record HomeEnvironmentDto(
            String statusLevel,
            String label,
            BigDecimal temperatureC,
            BigDecimal humidityPercent,
            String lastObservedAt) {
    }

    public record ScheduleDto(
            String id,
            String recordType,
            String title,
            String startsAt,
            String endsAt,
            String location,
            String relatedPersonName,
            String status) {
    }

    public record MedicationResponseDto(
            String id,
            String medicationId,
            String medicationScheduleId,
            String scheduledAt,
            String respondedAt,
            String status,
            String responseText) {
    }

    public record MedicationProgressDto(
            int total,
            int confirmed,
            int noResponse,
            int upcoming,
            int missed) {
    }

    public record ActivityDto(
            String id,
            String title,
            String summary,
            String occurredAt,
            String source,
            String statusLevel) {
    }
}
