package com.ssafy.bomi.guardian;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.fact.web.FactCandidateDto;
import com.ssafy.bomi.fact.web.FactCandidateMapper;
import com.ssafy.bomi.guardian.dto.DashboardResponse;
import com.ssafy.bomi.guardian.dto.DashboardResponse.ActivityDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.ElderDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.HomeEnvironmentDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.MedicationProgressDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.MedicationResponseDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.RobotDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.ScheduleDto;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 가디언 대시보드 집계 서비스. 여러 도메인(robot / care_record / fact_candidate /
 * conversation_summary / memory)을 한 응답으로 모은다. 단일 어르신 전제(P0).
 */
@Service
public class DashboardService {

    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
    private static final String SENIOR_USER_TYPE = "SENIOR";
    private static final Set<String> SCHEDULE_TYPES = Set.of("APPOINTMENT", "PERSONAL_SCHEDULE");

    /** 확인요청 목록에 노출할 대기 계열 상태. (P0 필드매핑 A-3) */
    private static final List<FactCandidateStatus> PENDING_STATUSES = List.of(
            FactCandidateStatus.NEEDS_CONFIRMATION,
            FactCandidateStatus.NEEDS_CLARIFICATION,
            FactCandidateStatus.COORDINATION_REQUIRED);

    private final AppUserRepository appUserRepository;
    private final RobotRepository robotRepository;
    private final CareRecordRepository careRecordRepository;
    private final FactCandidateRepository factCandidateRepository;
    private final MemoryRepository memoryRepository;
    private final ConversationSummaryRepository conversationSummaryRepository;
    private final FactCandidateMapper factCandidateMapper;

    public DashboardService(
            AppUserRepository appUserRepository,
            RobotRepository robotRepository,
            CareRecordRepository careRecordRepository,
            FactCandidateRepository factCandidateRepository,
            MemoryRepository memoryRepository,
            ConversationSummaryRepository conversationSummaryRepository,
            FactCandidateMapper factCandidateMapper) {
        this.appUserRepository = appUserRepository;
        this.robotRepository = robotRepository;
        this.careRecordRepository = careRecordRepository;
        this.factCandidateRepository = factCandidateRepository;
        this.memoryRepository = memoryRepository;
        this.conversationSummaryRepository = conversationSummaryRepository;
        this.factCandidateMapper = factCandidateMapper;
    }

    @Transactional(readOnly = true)
    public DashboardResponse getDashboard() {
        AppUser senior = appUserRepository.findFirstByUserType(SENIOR_USER_TYPE)
                .orElseThrow(() -> new IllegalStateException("등록된 어르신이 없습니다."));
        UUID seniorId = senior.getId();
        OffsetDateTime now = OffsetDateTime.now();
        LocalDate today = LocalDate.now(SEOUL);

        Robot robot = robotRepository.findBySeniorId(seniorId).orElse(null);
        List<CareRecord> records = careRecordRepository.findBySeniorId(seniorId);

        List<ScheduleDto> schedules = buildSchedules(records, today);
        List<MedicationResponseDto> medicationResponses = buildMedicationResponses(records, today, now);
        MedicationProgressDto progress = buildProgress(medicationResponses);

        List<FactCandidate> pending =
                factCandidateRepository.findBySeniorIdAndStatusInOrderByCreatedAtDesc(seniorId, PENDING_STATUSES);
        List<FactCandidateDto> confirmations = pending.stream().map(factCandidateMapper::toDto).toList();

        List<ActivityDto> activities = buildActivities(seniorId);

        ElderDto elder = new ElderDto(
                seniorId.toString(),
                displayName(senior),
                "NORMAL",
                "편안히 생활 중",
                iso(now));

        return new DashboardResponse(
                elder,
                toRobotDto(robot, seniorId),
                toEnvironmentDto(robot),
                confirmations.size(),
                schedules,
                medicationResponses,
                progress,
                confirmations.size(),
                confirmations,
                activities,
                iso(now));
    }

    // --- 일정 --------------------------------------------------------------

    private List<ScheduleDto> buildSchedules(List<CareRecord> records, LocalDate today) {
        List<ScheduleDto> result = new ArrayList<>();
        for (CareRecord r : records) {
            if (r.getStatus() != CareRecordStatus.ACTIVE) {
                continue;
            }
            if (!SCHEDULE_TYPES.contains(r.getRecordType())) {
                continue;
            }
            Map<String, Object> d = r.getDetails();
            OffsetDateTime startsAt = parseDateTime(str(d, "startsAt"));
            if (startsAt == null || !startsAt.atZoneSameInstant(SEOUL).toLocalDate().equals(today)) {
                continue;
            }
            result.add(new ScheduleDto(
                    r.getId().toString(),
                    r.getRecordType(),
                    str(d, "title"),
                    str(d, "startsAt"),
                    str(d, "endsAt"),
                    str(d, "location"),
                    str(d, "relatedPersonName"),
                    r.getStatus().name()));
        }
        result.sort(Comparator.comparing(
                (ScheduleDto s) -> parseDateTime(s.startsAt()),
                Comparator.nullsLast(Comparator.naturalOrder())));
        return result;
    }

    // --- 복약 응답 ---------------------------------------------------------
    // 스케줄(MEDICATION_SCHEDULE)의 오늘 복용 시각을 펼치고, 복용 기록(MEDICATION_TAKEN)과 매칭한다.

    private List<MedicationResponseDto> buildMedicationResponses(
            List<CareRecord> records, LocalDate today, OffsetDateTime now) {
        List<CareRecord> schedules = records.stream()
                .filter(r -> r.getStatus() == CareRecordStatus.ACTIVE)
                .filter(r -> "MEDICATION_SCHEDULE".equals(r.getRecordType()))
                .toList();
        List<CareRecord> taken = records.stream()
                .filter(r -> "MEDICATION_TAKEN".equals(r.getRecordType()))
                .toList();

        List<MedicationResponseDto> result = new ArrayList<>();
        for (CareRecord schedule : schedules) {
            Map<String, Object> d = schedule.getDetails();
            String medicationName = str(d, "medicationName");
            for (String localTime : stringList(d, "localTimes")) {
                OffsetDateTime scheduledAt = atTime(today, localTime);
                if (scheduledAt == null) {
                    continue;
                }
                CareRecord match = findTaken(taken, medicationName, scheduledAt);
                result.add(toMedicationResponse(schedule, medicationName, scheduledAt, match, now));
            }
        }
        result.sort(Comparator.comparing(
                (MedicationResponseDto m) -> parseDateTime(m.scheduledAt()),
                Comparator.nullsLast(Comparator.naturalOrder())));
        return result;
    }

    private MedicationResponseDto toMedicationResponse(
            CareRecord schedule,
            String medicationName,
            OffsetDateTime scheduledAt,
            CareRecord takenRecord,
            OffsetDateTime now) {
        String scheduleId = schedule.getId().toString();
        String medicationId = schedule.getParentRecordId() == null
                ? null : schedule.getParentRecordId().toString();
        String id = scheduleId + "@" + scheduledAt.toInstant();

        if (takenRecord != null) {
            Map<String, Object> td = takenRecord.getDetails();
            boolean declined = "DECLINED".equalsIgnoreCase(str(td, "outcome"));
            return new MedicationResponseDto(
                    id,
                    medicationId,
                    scheduleId,
                    iso(scheduledAt),
                    str(td, "respondedAt"),
                    declined ? "DECLINED" : "CONFIRMED",
                    str(td, "responseText"));
        }
        // 응답 없음: 시각 상대 상태(FE도 동일 규칙으로 재파생).
        String status = scheduledAt.isAfter(now) ? "UPCOMING" : "MISSED";
        String responseText = medicationName == null ? null : medicationName + " 복약 알림";
        return new MedicationResponseDto(id, medicationId, scheduleId, iso(scheduledAt), null, status, responseText);
    }

    private CareRecord findTaken(List<CareRecord> taken, String medicationName, OffsetDateTime scheduledAt) {
        for (CareRecord t : taken) {
            Map<String, Object> td = t.getDetails();
            OffsetDateTime ts = parseDateTime(str(td, "scheduledAt"));
            if (ts == null || !ts.toInstant().equals(scheduledAt.toInstant())) {
                continue;
            }
            String name = str(td, "medicationName");
            if (medicationName == null || medicationName.equals(name)) {
                return t;
            }
        }
        return null;
    }

    private MedicationProgressDto buildProgress(List<MedicationResponseDto> responses) {
        int total = responses.size();
        int confirmed = (int) responses.stream().filter(r -> "CONFIRMED".equals(r.status())).count();
        int upcoming = (int) responses.stream().filter(r -> "UPCOMING".equals(r.status())).count();
        int missed = (int) responses.stream().filter(r -> "MISSED".equals(r.status())).count();
        return new MedicationProgressDto(total, confirmed, 0, upcoming, missed);
    }

    // --- 최근 알게 된 것 (요약 + 기억) --------------------------------------

    private List<ActivityDto> buildActivities(UUID seniorId) {
        record Timed(ActivityDto dto, OffsetDateTime at) {
        }
        List<Timed> merged = new ArrayList<>();

        for (ConversationSummary s : conversationSummaryRepository.findTop5BySeniorIdOrderByGeneratedAtDesc(seniorId)) {
            merged.add(new Timed(
                    new ActivityDto(
                            s.getId().toString(),
                            "대화 요약",
                            s.getContent(),
                            iso(s.getGeneratedAt()),
                            "AI",
                            "NORMAL"),
                    s.getGeneratedAt()));
        }
        for (Memory m : memoryRepository.findTop5BySeniorIdAndLifecycleStatusOrderByFirstObservedAtDesc(
                seniorId, MemoryLifecycleStatus.ACTIVE)) {
            merged.add(new Timed(
                    new ActivityDto(
                            m.getId().toString(),
                            "새로 기억한 내용",
                            m.getContent(),
                            iso(m.getFirstObservedAt()),
                            "AI",
                            "NORMAL"),
                    m.getFirstObservedAt()));
        }

        return merged.stream()
                .sorted(Comparator.comparing(Timed::at, Comparator.nullsLast(Comparator.reverseOrder())))
                .limit(5)
                .map(Timed::dto)
                .toList();
    }

    // --- 로봇 / 환경 -------------------------------------------------------

    private RobotDto toRobotDto(Robot robot, UUID seniorId) {
        if (robot == null) {
            return new RobotDto(null, seniorId.toString(), null, null, false, null, null, null);
        }
        return new RobotDto(
                robot.getId().toString(),
                seniorId.toString(),
                robot.getDeviceId(),
                robot.getCurrentMode() == null ? null : robot.getCurrentMode().name(),
                robot.isActive(),
                robot.getAmbientTemperatureC(),
                robot.getAmbientHumidityPercent(),
                iso(robot.getAmbientObservedAt()));
    }

    private HomeEnvironmentDto toEnvironmentDto(Robot robot) {
        if (robot == null) {
            return new HomeEnvironmentDto("NORMAL", "환경 정보 없음", null, null, null);
        }
        return new HomeEnvironmentDto(
                "NORMAL",
                "실내 환경",
                robot.getAmbientTemperatureC(),
                robot.getAmbientHumidityPercent(),
                iso(robot.getAmbientObservedAt()));
    }

    // --- 공통 유틸 ---------------------------------------------------------

    private static String displayName(AppUser user) {
        return user.getPreferredName() != null ? user.getPreferredName() : user.getName();
    }

    private static OffsetDateTime atTime(LocalDate date, String localTime) {
        if (localTime == null) {
            return null;
        }
        try {
            return ZonedDateTime.of(date, LocalTime.parse(localTime), SEOUL).toOffsetDateTime();
        } catch (RuntimeException e) {
            return null;
        }
    }

    private static OffsetDateTime parseDateTime(String value) {
        if (value == null) {
            return null;
        }
        try {
            return OffsetDateTime.parse(value);
        } catch (RuntimeException e) {
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private static List<String> stringList(Map<String, Object> map, String key) {
        if (map == null) {
            return List.of();
        }
        Object v = map.get(key);
        if (v instanceof List<?> list) {
            return list.stream().map(o -> o == null ? null : o.toString()).filter(s -> s != null).toList();
        }
        return List.of();
    }

    private static String str(Map<String, Object> map, String key) {
        if (map == null) {
            return null;
        }
        Object v = map.get(key);
        return v == null ? null : v.toString();
    }

    private static String iso(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }
}
