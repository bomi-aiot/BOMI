package com.ssafy.bomi.guardian;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.domain.NotificationTier;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.fact.domain.FactCandidate;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.fact.web.FactCandidateDto;
import com.ssafy.bomi.fact.web.FactCandidateMapper;
import com.ssafy.bomi.guardian.dto.DashboardResponse;
import com.ssafy.bomi.guardian.dto.DashboardResponse.ActivityDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.ElderDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.GuardianDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.HomeEnvironmentDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.MedicationProgressDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.MedicationResponseDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.RobotDto;
import com.ssafy.bomi.guardian.dto.DashboardResponse.ScheduleDto;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.relationship.domain.RelationshipPriority;
import com.ssafy.bomi.relationship.domain.RelationshipStatus;
import com.ssafy.bomi.relationship.repository.CareRelationshipRepository;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.MedicationReminderProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioStatus;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Stream;
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
     * 활동 피드 공개범위 계약 버전. buildActivities 가 건별 visibility 를 채워 보낼 때만
     * 이 값을 실을 수 있다 — 값과 계약이 같이 움직여야 FE 가 "확인했다"고 읽어도 된다.
     */
    private static final String ACTIVITY_VISIBILITY_CONTRACT = "GUARDIAN_VISIBLE_V1";

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

    /**
     * 활동 피드에 싣는 "덜 급한" 항목(기억·T2 알림)의 상한.
     *
     * <p>위급(T1)에는 걸지 않는다 — {@link #buildActivities} 참고.</p>
     */
    private static final int ACTIVITY_LIMIT = 5;

    /** 확인요청 목록에 노출할 대기 계열 상태. (P0 필드매핑 A-3) */
    private static final List<FactCandidateStatus> PENDING_STATUSES = List.of(
            FactCandidateStatus.NEEDS_CONFIRMATION,
            FactCandidateStatus.NEEDS_CLARIFICATION,
            FactCandidateStatus.COORDINATION_REQUIRED);

    /**
     * "아직 끝나지 않은" 시나리오 상태. 종료 4값의 여집합으로 잡는다.
     *
     * <p>여집합으로 쓰는 이유 — ScenarioStatus 에 진행 상태가 새로 늘어날 때
     * (산책의 STARTING_FOLLOW/FOLLOWING 이 그렇게 늘었다) 이 목록을 고치는 것을
     * 잊으면 그 시나리오만 화면에서 조용히 사라진다. 종료 상태는 거의 늘지 않는다.</p>
     */
    private static final Set<ScenarioStatus> ACTIVE_SCENARIO_STATUSES =
            EnumSet.complementOf(EnumSet.of(
                    ScenarioStatus.COMPLETED,
                    ScenarioStatus.FAILED,
                    ScenarioStatus.CANCELLED,
                    ScenarioStatus.TIMED_OUT));

    private final AppUserRepository appUserRepository;
    private final RobotRepository robotRepository;
    private final CareRecordRepository careRecordRepository;
    private final FactCandidateRepository factCandidateRepository;
    private final MemoryRepository memoryRepository;
    private final ScenarioRepository scenarioRepository;
    private final FactCandidateMapper factCandidateMapper;

    private final CareRelationshipRepository careRelationshipRepository;

    /**
     * 복약 알림 창 설정.
     *
     * <p>읽기 전용 조회 서비스가 시나리오 설정을 참조하는 것이 어색해 보이지만, 그것이
     * 정확히 이 값의 성격이다 — "보호자 화면이 이 슬롯을 놓쳤다고 말해도 되는 시각"은
     * "로봇이 더는 묻지 않는 시각"과 같아야 한다. 이 숫자를 읽기 모델에 따로 적어 두면
     * 한쪽만 바뀌는 날 화면과 로봇의 말이 조용히 어긋난다.</p>
     */
    private final MedicationReminderProperties medicationReminderProperties;

    public DashboardService(
            AppUserRepository appUserRepository,
            RobotRepository robotRepository,
            CareRecordRepository careRecordRepository,
            FactCandidateRepository factCandidateRepository,
            MemoryRepository memoryRepository,
            ScenarioRepository scenarioRepository,
            FactCandidateMapper factCandidateMapper,
            CareRelationshipRepository careRelationshipRepository,
            MedicationReminderProperties medicationReminderProperties) {
        this.appUserRepository = appUserRepository;
        this.robotRepository = robotRepository;
        this.careRecordRepository = careRecordRepository;
        this.factCandidateRepository = factCandidateRepository;
        this.memoryRepository = memoryRepository;
        this.scenarioRepository = scenarioRepository;
        this.factCandidateMapper = factCandidateMapper;
        this.careRelationshipRepository = careRelationshipRepository;
        this.medicationReminderProperties = medicationReminderProperties;
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
                primaryGuardian(seniorId),
                toRobotDto(robot, seniorId),
                toEnvironmentDto(robot),
                countTodayIncidents(records, today),
                schedules,
                medicationResponses,
                progress,
                confirmations.size(),
                confirmations,
                activities,
                ACTIVITY_VISIBILITY_CONTRACT,
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
        //
        // ★ 예정 시각을 1분 지났다고 곧바로 '놓침'이 아니다.
        //   로봇의 알림 창은 [예정 - reminderLeadMinutes, 예정 + graceMinutes) 이고
        //   (MedicationReminderScheduler.remindIfDue), 그 안에서는 아직 어르신께 묻는
        //   중이거나 곧 물어본다. 그 시간에 보호자 화면이 경고색으로 "아직 응답이
        //   확인되지 않았어요" 를 띄우면, 정상 진행을 실패로 읽게 만든다 — 매일 뜨는
        //   거짓 경고는 진짜 경고까지 같이 죽인다.
        //
        //   graceMinutes 를 여기에 숫자로 다시 적지 않고 스케줄러와 같은 설정을 읽는다.
        //   두 곳에 15를 적어 두면 한쪽만 바뀌는 날 조용히 어긋난다.
        OffsetDateTime reminderWindowEnd =
                scheduledAt.plusMinutes(medicationReminderProperties.getGraceMinutes());
        String status = now.isBefore(reminderWindowEnd) ? "UPCOMING" : "MISSED";
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

    // --- 최근 알게 된 것 (기억) ----------------------------------------------
    //
    // 대화 요약(conversation_summary)은 여기 섞지 않는다 (S15P11E102-254, CLAUDE.md §9
    // T4). 요약은 로봇이 "지난 대화"를 참고하기 위한 원문 압축이지, 보호자에게 읽어
    // 주려고 만드는 것이 아니다 — memory 처럼 visibility 로 건별 공개 여부를 고르는
    // 장치가 요약에는 없다. 예전에는 요약이 0건이라 우연히 무해했을 뿐이다: 이
    // 티켓이 요약을 실제로 채우기 시작하면 그 우연이 사라진다.

    private List<ActivityDto> buildActivities(UUID seniorId) {
        record Timed(ActivityDto dto, OffsetDateTime at, boolean urgent) {
        }
        List<Timed> merged = new ArrayList<>();

        // S15P11E102-262: 가시성 필터 없는 findTop5...는 PRIVATE 기억까지 그대로
        // 돌려준다 — "이건 나만 알고 있을래요"라고 답한 내용이 보호자 화면에 새던
        // 경로가 이것이었다. 씨앗이 2건뿐이던 지금까지는 우연히 조용했을 뿐이다.
        for (Memory m : memoryRepository.findVisibleToGuardianBySeniorIdAndLifecycleStatus(
                seniorId, MemoryLifecycleStatus.ACTIVE, GUARDIAN_VISIBLE_MEMORY_VISIBILITIES,
                PageRequest.of(0, ACTIVITY_LIMIT))) {
            merged.add(new Timed(
                    new ActivityDto(
                            m.getId().toString(),
                            "새로 기억한 내용",
                            m.getContent(),
                            iso(m.getFirstObservedAt()),
                            "AI",
                            "NORMAL",
                            m.getVisibility() == null ? null : m.getVisibility().name()),
                    m.getFirstObservedAt(),
                    false));
        }

        // 로봇이 올린 알림. T1 과 T2 가 화면에서 구분되어야 한다 (S15P11E102-211).
        //
        // 왜 활동 피드에 섞는가
        //   보호자가 보는 시간순 흐름이 이미 여기다. 알림만 따로 두면 "오늘 무슨 일이
        //   있었나"를 두 곳에서 읽어야 하고, 그 둘의 시간 순서를 사람이 맞춰야 한다.
        //
        // 구분은 statusLevel 로 한다. T1 은 지금 조치가 필요한 것이고, T2 는 추세다.
        // 둘을 같은 무게로 보여주면 매일 오는 요약이 응급을 가린다 (CLAUDE.md §9).
        // 공유 동의가 없으면 T2 는 화면에도 올리지 않는다.
        //
        // ★ 왜 이 필터가 지금 생겼나 (S15P11E102-362 리뷰 지적)
        //   GuardianAlertService.accept 는 동의가 없을 때 알림을 '보류'한다 — 행은 남기고
        //   delivered=false 만 돌려준다("관찰을 잃지 않되 공유하지 않는다"). 그런데 이
        //   조회는 recipient_guardian_id 도 동의도 보지 않아서, 보류된 행이 그대로 활동
        //   피드에 실렸다. 지금까지 무해했던 이유는 단 하나 — T2 를 만드는 호출자가
        //   0건이라 그런 행이 존재한 적이 없어서다. 일일 요약 발송 스케줄러가 그 전제를
        //   깬다: 동의하지 않은 어르신에게도 매일 한 행씩 쌓인다.
        //
        //   지표 값 자체는 고정 문구에 가려 안 나가지만, "요약이 만들어졌다"는 사실과
        //   그 시각이 매일 보호자에게 전달된다. 동의하지 않은 것을 공유하지 않겠다는
        //   약속은 그 정도로도 깨진다.
        //
        //   recipient_guardian_id 로 거르지 않는 이유: NO_GUARDIAN 경로도 그 값이 null 인데,
        //   그쪽은 "보호자가 연결되는 순간 보이게 하려고" 일부러 남긴 것이다. 그 의도를
        //   죽이지 않으려면 거를 축은 수신자가 아니라 동의여야 한다.
        //
        //   T1 은 동의 면제다(NotificationTier 자바독) — 응급은 동의를 기다리지 않는다.
        boolean sharingGranted = appUserRepository.findById(seniorId)
                .map(user -> user.getGuardianSharingConsentStatus() == ConsentStatus.GRANTED)
                .orElse(false);

        // ★ 같은 사유의 T2 는 최신 1건만 싣는다.
        //
        //   현관 노드는 연결이 끊길 때마다 T2 를 한 건씩 올린다 — 실서버에 오늘 하루만
        //   door_node_offline 이 여덟 건 쌓였다. 피드 상한이 5건이라 그대로 두면 똑같은
        //   문장 다섯 줄이 기억과 하루 요약을 전부 밀어낸다. 보호자가 얻는 정보는 한 줄과
        //   다르지 않으면서 나머지를 잃는 교환이다.
        //
        //   T1 은 묶지 않는다. 응급은 사유가 같아도 건마다 별개의 사건이다.
        List<CareRecord> alertsToShow = new ArrayList<>();
        Map<String, CareRecord> latestT2ByReason = new LinkedHashMap<>();
        for (CareRecord alert : careRecordRepository.findBySeniorIdAndRecordTypeAndStatus(
                seniorId, GUARDIAN_ALERT_TYPE, CareRecordStatus.ACTIVE)) {
            NotificationTier tier = alert.getNotificationTier();
            if (tier == null) {
                continue;
            }
            if (tier == NotificationTier.T1) {
                alertsToShow.add(alert);
                continue;
            }
            if (!sharingGranted) {
                continue;
            }
            String reason = str(alert.getDetails(), "reason");
            latestT2ByReason.merge(
                    reason == null ? "" : reason,
                    alert,
                    (kept, incoming) -> isLater(alertTime(incoming), alertTime(kept)) ? incoming : kept);
        }
        alertsToShow.addAll(latestT2ByReason.values());

        for (CareRecord alert : alertsToShow) {
            NotificationTier tier = alert.getNotificationTier();
            OffsetDateTime at = alertTime(alert);
            merged.add(new Timed(
                    new ActivityDto(
                            alert.getId().toString(),
                            alertTitle(alert, tier),
                            alertSummary(alert, tier),
                            iso(at),
                            "로봇",
                            tier == NotificationTier.T1 ? "URGENT" : "INFO",
                            // 보호자에게 보내려고 만든 기록이다. memory 처럼 건별 공개범위
                            // 컬럼이 없으므로 여기서 그 사실을 명시한다.
                            "SHARED_WITH_PRIMARY"),
                    at,
                    tier == NotificationTier.T1));
        }

        // ★ T1(위급)은 상한에 걸려 사라지지 않는다.
        //
        //   이전에는 기억과 알림을 한 줄에 세워 시간순 5건으로 잘랐다. 그러면 위급
        //   알림보다 새로운 기억이 다섯 건만 쌓여도 그 알림이 응답에서 통째로 빠진다.
        //   가디언웹은 이 피드 안의 URGENT 만 보고 안전 알림을 그리므로(FE
        //   mappers/dashboard.ts), 화면은 "지금 확인이 필요한 일은 없어요" 로 돌아가고
        //   새 알림 토스트도 뜨지 않는다. 게다가 한 번 밀려난 알림은 기억이 더 쌓일수록
        //   영영 돌아오지 않는다 — 조용히, 되돌릴 수 없이 알림을 잃는 경로였다.
        //   (실서버에서 이미 그 상태였다: 피드 5칸이 전부 기억이었다.)
        //
        //   그래서 상한은 "덜 급한 것"에만 건다. 위급이 여섯 건이면 여섯 건 다 나가고
        //   피드가 잠깐 길어지는 편이, 여섯 번째를 안 보여 주는 것보다 낫다.
        //
        //   T2 는 여기서 보호하지 않는다 — 위의 사유별 최신 1건 접기가 이미 그쪽의
        //   폭주(door_node_offline 여덟 건)를 막고 있고, T2 는 놓쳐도 되돌릴 수 있다.
        Comparator<Timed> newestFirst =
                Comparator.comparing(Timed::at, Comparator.nullsLast(Comparator.reverseOrder()));
        List<Timed> urgent = merged.stream().filter(Timed::urgent).toList();
        List<Timed> rest = merged.stream()
                .filter(timed -> !timed.urgent())
                .sorted(newestFirst)
                .limit(Math.max(0, ACTIVITY_LIMIT - urgent.size()))
                .toList();

        return Stream.concat(urgent.stream(), rest.stream())
                .sorted(newestFirst)
                .map(Timed::dto)
                .toList();
    }

    // --- 로봇 / 환경 -------------------------------------------------------

    private RobotDto toRobotDto(Robot robot, UUID seniorId) {
        if (robot == null) {
            return new RobotDto(
                    null, seniorId.toString(), null, null, false, null, null, null, null, null);
        }
        Scenario active = activeScenarioOrNull(robot.getId());
        return new RobotDto(
                robot.getId().toString(),
                seniorId.toString(),
                robot.getDeviceId(),
                robot.getCurrentMode() == null ? null : robot.getCurrentMode().name(),
                robot.isActive(),
                robot.getAmbientTemperatureC(),
                robot.getAmbientHumidityPercent(),
                iso(robot.getAmbientObservedAt()),
                active == null || active.getScenarioType() == null
                        ? null : active.getScenarioType().name(),
                active == null ? null : iso(active.getCreatedAt()));
    }

    /**
     * 이 로봇에서 지금 진행 중인 시나리오 하나. 없으면 null.
     *
     * <p>정상 상태에서는 로봇 하나에 활성 시나리오가 하나다(ACTIVE_SCENARIO_EXISTS 가
     * 두 번째 시작을 막는다). 그래도 리스트로 받는 조회를 쓰는 이유는, 리셋이 덜 된
     * 잔여물이 남아 있을 수 있어서다 — 그럴 땐 가장 최근에 갱신된 것을 보여준다.</p>
     *
     * <p>읽기 전용 집계이므로 잠금(ForUpdate) 계열 조회를 쓰지 않는다.</p>
     */
    private Scenario activeScenarioOrNull(UUID robotId) {
        List<Scenario> active = scenarioRepository
                .findByRobotIdAndFinalStatusInOrderByUpdatedAtDesc(
                        robotId, ACTIVE_SCENARIO_STATUSES);
        return active.isEmpty() ? null : active.get(0);
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

    /**
     * 이 어르신의 1차 보호자.
     *
     * <p>이미 있는 조회를 그대로 쓴다 — T1 알림·일일 요약이 "받을 사람"을 찾을 때 쓰는
     * 바로 그 관계다(CareRelationshipRepository). 화면 상단에 띄우는 이름이 알림을 받는
     * 사람과 다르면, 보호자는 자기가 받는 줄 알고 안 오는 알림을 기다리게 된다.</p>
     *
     * <p>연결된 보호자가 없거나 그 계정을 못 찾으면 null 이다. 온보딩 중인 어르신에게
     * 실제로 있는 상태이고, 화면은 이름 자리를 비우는 것으로 그 사실을 말한다.</p>
     */
    private GuardianDto primaryGuardian(UUID seniorId) {
        return careRelationshipRepository
                .findFirstBySeniorIdAndPriorityAndStatus(
                        seniorId, RelationshipPriority.PRIMARY, RelationshipStatus.ACTIVE)
                .flatMap(relationship -> appUserRepository.findById(relationship.getGuardianId())
                        .map(guardian -> new GuardianDto(
                                guardian.getId().toString(),
                                displayName(guardian),
                                RelationshipPriority.PRIMARY.name())))
                .orElse(null);
    }

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
     * 오늘 올라온 보호자 알림(T1+T2) 건수.
     *
     * <p>이 자리에는 {@code confirmations.size()} 가 들어 있었다 — 바로 아래
     * {@code pendingConfirmationCount} 와 <b>같은 값</b>을 "오늘 이상 징후"라는 이름으로
     * 내보내고 있었다는 뜻이다. 지금은 화면이 이 필드를 읽지 않아 아무 증상이 없지만,
     * 이름을 믿고 쓰는 사람이 나오는 날 조용히 틀린다. 값이 이름을 배신하는 필드는
     * 없는 필드보다 나쁘다 — 틀렸다는 사실조차 눈에 띄지 않기 때문이다.</p>
     *
     * <p>세는 축을 알림으로 잡는 이유는, 보호자가 "오늘 무슨 일이 있었나"를 물을 때
     * 답이 되는 것이 확인 대기 건수가 아니라 로봇이 올린 알림이기 때문이다. 여기서는
     * 등급을 나누지 않는다 — 등급별 표시는 안전 알림 카드와 활동 피드가 이미 한다.</p>
     */
    private static int countTodayIncidents(List<CareRecord> records, LocalDate today) {
        return (int) records.stream()
                .filter(r -> GUARDIAN_ALERT_TYPE.equals(r.getRecordType()))
                .filter(r -> r.getStatus() == CareRecordStatus.ACTIVE)
                .filter(r -> {
                    OffsetDateTime at = alertTime(r);
                    // 시각을 모르는 기록은 "오늘"이라고 단정하지 않는다.
                    return at != null && at.atZoneSameInstant(SEOUL).toLocalDate().equals(today);
                })
                .count();
    }

    /** 둘 중 어느 쪽이 더 최근인가. null 은 "모르는 시각"이라 이기지 못한다. */
    private static boolean isLater(OffsetDateTime candidate, OffsetDateTime current) {
        if (candidate == null) {
            return false;
        }
        return current == null || candidate.isAfter(current);
    }

    /**
     * 활동 피드의 제목.
     *
     * <p>T2 를 전부 "하루 요약"으로 부르던 것을 사유로 가른다 — 현관 센서 오프라인 알림에
     * "하루 요약"이라는 이름을 붙이면 보호자는 매일 오는 정기 보고로 읽고 넘긴다.
     * 실제로 T2 를 만드는 곳은 일일 요약 스케줄러 하나가 아니라 로봇의 알림 API 도 있다.</p>
     */
    private static String alertTitle(CareRecord alert, NotificationTier tier) {
        if (tier == NotificationTier.T1) {
            return "확인이 필요해요";
        }
        return "daily_summary".equals(str(alert.getDetails(), "reason")) ? "하루 요약" : "알아두면 좋아요";
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
                case "emergency" -> emergencySummary(alert);
                default -> "확인이 필요한 일이 있었어요.";
            };
        }
        // T2 도 사유별로 가른다. 고정 한 줄이던 시절에는 현관 센서 문제와 일일 요약이
        // 화면에서 한 글자도 다르지 않았다 — T1 에서 이미 한 번 고친 실수다.
        return switch (reason == null ? "" : reason) {
            case "daily_summary" -> "오늘 하루 요약이 도착했어요.";
            case "door_node_offline" -> "현관 센서와 연결이 끊겨 있었어요.";
            case "door_left_open" -> "현관문이 한동안 열려 있었어요.";
            default -> "보미가 확인해 둔 일이 있어요.";
        };
    }

    /**
     * reason = "emergency" 인 T1 의 문구.
     *
     * <p>이 사유가 여기 없었던 동안, 로봇이 증상을 듣고 확인까지 거쳐 올린 알림이
     * 보호자 화면에 "확인이 필요한 일이 있었어요."로 떴다. 사유를 안다는 사실을
     * 알면서 모른다고 말하는 문구였다.</p>
     *
     * <p>왜 {@code confirmed_by} 로 두 갈래를 나누는가 — 이 둘은 보호자가 해야 할
     * 일이 다르다. 어르신이 "그렇다"고 답한 것은 상황을 아는 상태이고, 답이 없는
     * 것은 아무도 지금 상태를 모르는 상태다. 후자가 더 급하다. 같은 문장으로
     * 뭉개면 그 차이가 화면에서 사라진다.</p>
     *
     * <p>증상 자체는 쓰지 않는다("가슴이 아프다고 하셨어요"). 로봇이 원문도
     * 부위도 보내지 않기 때문이다 — 없는 것을 지어내면 그 순간부터 이 화면은
     * 근거가 아니라 추측이 된다 (CLAUDE.md §9).</p>
     */
    private static String emergencySummary(CareRecord alert) {
        String confirmedBy = str(alert.getDetails(), "confirmed_by");
        return switch (confirmedBy == null ? "" : confirmedBy) {
            case "senior_reply" -> "몸이 불편하다고 하셨고, 확인 요청에 그렇다고 답하셨어요.";
            case "no_reply_to_safety_check" -> "몸이 불편하다고 하신 뒤 확인 질문에 답이 없으셨어요.";
            default -> "몸이 불편하다고 하셨어요.";
        };
    }

    private static String iso(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }
}
