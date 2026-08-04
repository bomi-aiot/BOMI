package com.ssafy.bomi.guardian;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.domain.NotificationTier;
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
import com.ssafy.bomi.memory.domain.MemoryVisibility;
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
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
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
    /** 로봇이 올린 보호자 알림의 기록 타입 (S15P11E102-211). */
    private static final String GUARDIAN_ALERT_TYPE = "GUARDIAN_ALERT";

    /**
     * 보호자 화면에 노출해도 되는 기억 가시성 (S15P11E102-262).
     *
     * <p>{@code PRIVATE} 은 일부러 뺐다 — {@link Memory#create(UUID, com.ssafy.bomi.memory.domain.MemoryType, String)}
     * 의 기본값이 {@code PRIVATE} 이고, 그게 바로 CLAUDE.md §9 가 말하는 T4("이건
     * 나만 알고 있을래요")를 실제로 만드는 값이다. 이 화면은 가디언 한 명을
     * 구분하지 않는 P0 단일 대시보드라서(guardianId 없음) PRIMARY 전용 값과
     * 전체공개 값을 나눌 근거가 없다 — 그래서 "PRIVATE 만 아니면 허용"으로 묶는다.
     * 아직 이 어르신-보호자 여러 쌍을 구분해야 하는 시점이 되면, 요청자별로
     * {@link com.ssafy.bomi.context.application.ConversationContextService#resolveVisibility}
     * 가 하는 것과 같은 분기가 여기도 필요해진다.</p>
     */
    private static final Set<MemoryVisibility> GUARDIAN_VISIBLE_MEMORY_VISIBILITIES =
        EnumSet.of(MemoryVisibility.SHARED_WITH_PRIMARY, MemoryVisibility.SHARED_WITH_GUARDIANS);

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

    /**
     * 이 복약 슬롯에 해당하는 복용 기록을 찾는다.
     *
     * <p>occurred_at 으로 맞춘다 (S15P11E102-230). MEDICATION_TAKEN 의 occurred_at 은
     * '매칭된 슬롯 시각'이고, 실제로 대답한 순간은 details.respondedAt 에 그대로 있다.
     * 예전에는 details.scheduledAt 을 파싱해 비교했는데, 같은 값을 문자열로 다시 읽는
     * 일이었다.</p>
     */
    private CareRecord findTaken(List<CareRecord> taken, String medicationName, OffsetDateTime scheduledAt) {
        for (CareRecord t : taken) {
            OffsetDateTime ts = t.getOccurredAt();
            if (ts == null || !ts.toInstant().equals(scheduledAt.toInstant())) {
                continue;
            }
            String name = str(t.getDetails(), "medicationName");
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
        // S15P11E102-262: 가시성 필터 없는 findTop5...는 PRIVATE 기억까지 그대로
        // 돌려준다 — "이건 나만 알고 있을래요"라고 답한 내용이 보호자 화면에 새던
        // 경로가 이것이었다. 씨앗이 2건뿐이던 지금까지는 우연히 조용했을 뿐이다.
        for (Memory m : memoryRepository.findVisibleToGuardianBySeniorIdAndLifecycleStatus(
                seniorId, MemoryLifecycleStatus.ACTIVE, GUARDIAN_VISIBLE_MEMORY_VISIBILITIES,
                PageRequest.of(0, 5))) {
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

        // 로봇이 올린 알림. T1 과 T2 가 화면에서 구분되어야 한다 (S15P11E102-211).
        //
        // 왜 활동 피드에 섞는가
        //   보호자가 보는 시간순 흐름이 이미 여기다. 알림만 따로 두면 "오늘 무슨 일이
        //   있었나"를 두 곳에서 읽어야 하고, 그 둘의 시간 순서를 사람이 맞춰야 한다.
        //
        // 구분은 statusLevel 로 한다. T1 은 지금 조치가 필요한 것이고, T2 는 추세다.
        // 둘을 같은 무게로 보여주면 매일 오는 요약이 응급을 가린다 (CLAUDE.md §9).
        for (CareRecord alert : careRecordRepository.findBySeniorIdAndRecordTypeAndStatus(
                seniorId, GUARDIAN_ALERT_TYPE, CareRecordStatus.ACTIVE)) {
            NotificationTier tier = alert.getNotificationTier();
            if (tier == null) {
                continue;
            }
            OffsetDateTime at = alertTime(alert);
            merged.add(new Timed(
                    new ActivityDto(
                            alert.getId().toString(),
                            tier == NotificationTier.T1 ? "확인이 필요해요" : "하루 요약",
                            alertSummary(alert, tier),
                            iso(at),
                            "로봇",
                            tier == NotificationTier.T1 ? "URGENT" : "INFO"),
                    at));
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

    /**
     * 알림이 일어난 시각.
     *
     * <p>이제 컬럼 하나를 읽는다 (S15P11E102-230). 예전에는 로봇이 싣는 {@code ts}
     * (epoch 초)와 일일 요약이 싣는 {@code metricDate}(날짜)를 여기서 각각 파싱했다.
     * 두 규약을 V7 이 한 컬럼으로 합쳤고, 쓰는 쪽이 전부 컬럼에 적는다.</p>
     *
     * <p>null 이면 정렬에서 맨 뒤로 밀린다. 시각을 지어내면 어제 알림이 오늘 맨 위에
     * 뜨고, 보호자는 그것을 새 알림으로 읽는다.</p>
     */
    private static OffsetDateTime alertTime(CareRecord alert) {
        return alert.getOccurredAt();
    }

    /**
     * 보호자가 한 줄로 읽을 요약.
     *
     * <p>원문 발화는 애초에 payload 에 없다(로봇이 보내지 않는다). 여기서도 details 를
     * 통째로 펼치지 않는다 — 필드가 늘어날 때마다 화면에 알 수 없는 값이 새는 경로가
     * 된다. 보호자에게 필요한 것은 "가서 봐 주세요"이지 진단 근거가 아니다.</p>
     */
    private static String alertSummary(CareRecord alert, NotificationTier tier) {
        String reason = str(alert.getDetails(), "reason");
        if (tier == NotificationTier.T1) {
            return switch (reason == null ? "" : reason) {
                case "no_response" -> "한참 대답이 없으셨어요.";
                case "not_returned" -> "나가신 뒤 오래 돌아오지 않으셨어요.";
                case "self_harm_override" -> "마음이 많이 힘드신 것 같아요.";
                case "explicit_request" -> "직접 연락을 요청하셨어요.";
                default -> "확인이 필요한 일이 있었어요.";
            };
        }
        return "오늘 하루 요약이 도착했어요.";
    }

    private static String iso(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }
}
