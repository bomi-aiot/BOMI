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
        /**
         * 활동 피드 공개범위 계약 버전. FE 는 이 값이 {@code GUARDIAN_VISIBLE_V1} 일 때만
         * {@code recentActivities} 를 "확인된 목록"으로 읽고, 없으면 null(=확인 못 함)로
         * 취급한다. 지금까지 이 필드가 없어서 백엔드가 활동을 정상으로 내려주는데도
         * 화면은 항상 "아직 연결되지 않음"을 그렸다.
         */
        String activityVisibilityContract,
        String generatedAt) {

    public record ElderDto(
            String id,
            String displayName,
            String statusLevel,
            String statusLabel,
            String lastCheckedAt) {
    }

    /**
     * 로봇 현황.
     *
     * <p>{@code currentMode} 는 RobotMode(IDLE/SCENARIO_ACTIVE/REST_GUARD/SAFE_STOP)
     * 4값뿐이라 현관 인사·"보미야" 호출·복약 알림·산책이 모두 SCENARIO_ACTIVE 하나로
     * 뭉개진다. {@code activeScenarioType} 은 그 넷을 화면에서 구분하기 위한 값이며
     * scenario 테이블에서 온다. 진행 중인 시나리오가 없으면 두 값 모두 null 이다.</p>
     */
    public record RobotDto(
            String id,
            String elderId,
            String deviceId,
            String currentMode,
            boolean isActive,
            BigDecimal ambientTemperatureC,
            BigDecimal ambientHumidityPercent,
            String ambientObservedAt,
            String activeScenarioType,
            String activeScenarioStartedAt) {
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

    /**
     * 활동 1건. {@code visibility} 는 이 건을 보호자에게 보여도 되는지의 근거다 —
     * memory 는 자기 visibility 를 그대로 싣고, 로봇 알림은 보호자 수신용으로
     * 만들어진 것이라 SHARED_WITH_PRIMARY 로 표기한다. FE 는 이 값이 없는 건을
     * 그리지 않는다(PRIVATE 유출 방지).
     */
    public record ActivityDto(
            String id,
            String title,
            String summary,
            String occurredAt,
            String source,
            String statusLevel,
            String visibility) {
    }
}
