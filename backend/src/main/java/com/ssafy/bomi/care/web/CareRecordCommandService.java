package com.ssafy.bomi.care.web;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.domain.CareRecordTime;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.care.web.dto.MedicationDto;
import com.ssafy.bomi.care.web.dto.MedicationRequests.CreateMedicationRequest;
import com.ssafy.bomi.care.web.dto.MedicationRequests.UpdateMedicationRequest;
import com.ssafy.bomi.care.web.dto.ScheduleDto;
import com.ssafy.bomi.care.web.dto.ScheduleRequests.CreateScheduleRequest;
import com.ssafy.bomi.care.web.dto.ScheduleRequests.UpdateScheduleRequest;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * 돌봄기록 쓰기 서비스 — 복약/일정 등록·수정·삭제·토글. 단일 어르신 전제(P0).
 * 보호자가 직접 작성하는 케이스(처방 등록, 병원 예약)를 다룬다.
 */
@Service
public class CareRecordCommandService {

    private static final String SENIOR_USER_TYPE = "SENIOR";
    private static final String TZ = "Asia/Seoul";

    private final AppUserRepository appUserRepository;
    private final CareRecordRepository careRecordRepository;

    public CareRecordCommandService(
            AppUserRepository appUserRepository, CareRecordRepository careRecordRepository) {
        this.appUserRepository = appUserRepository;
        this.careRecordRepository = careRecordRepository;
    }

    // --- 복약 --------------------------------------------------------------

    @Transactional
    public MedicationDto createMedication(CreateMedicationRequest req) {
        UUID seniorId = seniorId();

        Map<String, Object> details = new HashMap<>();
        put(details, "medicationName", req.name());
        put(details, "dose", req.dosage());
        put(details, "instruction", req.instructions());
        put(details, "purpose", req.purpose());
        put(details, "activeIngredient", req.activeIngredient());
        put(details, "reminderEnabled", req.reminderEnabled());
        // occurred_at 을 두지 않는다 (S15P11E102-230).
        //
        // 처방 자체는 시간축의 한 점이 아니다. "혈압약을 드신다"는 사실이지 사건이 아니다.
        // 지금 시각으로 채우면 "오늘 일어난 일" 질의에 처방이 딸려 나온다.
        CareRecord med = careRecordRepository.save(
                CareRecord.create(seniorId, "MEDICATION", details));

        if (req.localTime() != null && !req.localTime().isBlank()) {
            Map<String, Object> schedDetails = new HashMap<>();
            put(schedDetails, "medicationName", req.name());
            schedDetails.put("localTimes", List.of(req.localTime()));
            schedDetails.put("timeZone", TZ);
            put(schedDetails, "reminderLeadMinutes", req.reminderLeadMinutes());

            // 스케줄도 occurred_at 이 없다. 반복 규칙이라 한 점으로 표현할 수 없고,
            // 전개는 recurrence 가 담당한다. 첫 회 시각으로 채우면 매일 반복되는 약이
            // 등록일 하루에만 있는 것처럼 집계된다.
            CareRecord sched = CareRecord.create(seniorId, "MEDICATION_SCHEDULE", schedDetails);
            sched.assignParent(med.getId());
            sched.updateRecurrence(dailyRecurrence(req.localTime()));
            careRecordRepository.save(sched);
            return CareRecordDtoMapper.toMedicationDto(med, List.of(sched));
        }
        return CareRecordDtoMapper.toMedicationDto(med, List.of());
    }

    @Transactional
    public MedicationDto updateMedication(UUID id, UpdateMedicationRequest req) {
        CareRecord med = load(id);
        Map<String, Object> details = new HashMap<>(med.getDetails());
        put(details, "medicationName", req.name());
        put(details, "dose", req.dosage());
        put(details, "instruction", req.instructions());
        put(details, "purpose", req.purpose());
        put(details, "activeIngredient", req.activeIngredient());
        put(details, "reminderEnabled", req.reminderEnabled());
        med.updateDetails(details);
        careRecordRepository.save(med);

        List<CareRecord> children = careRecordRepository.findByParentRecordId(med.getId());
        if (req.localTime() != null && !req.localTime().isBlank() && !children.isEmpty()) {
            CareRecord sched = children.get(0);
            Map<String, Object> sd = new HashMap<>(sched.getDetails());
            sd.put("localTimes", List.of(req.localTime()));
            sched.updateDetails(sd);
            sched.updateRecurrence(dailyRecurrence(req.localTime()));
            careRecordRepository.save(sched);
        }
        return CareRecordDtoMapper.toMedicationDto(med, children);
    }

    @Transactional
    public MedicationDto toggleMedicationStatus(UUID id) {
        CareRecord med = load(id);
        // ACTIVE ↔ CANCELLED (care_record 에 PAUSED 상태가 없어 '중지 = CANCELLED' 로 매핑).
        med.changeStatus(med.getStatus() == CareRecordStatus.ACTIVE
                ? CareRecordStatus.CANCELLED : CareRecordStatus.ACTIVE);
        careRecordRepository.save(med);
        return CareRecordDtoMapper.toMedicationDto(med, careRecordRepository.findByParentRecordId(id));
    }

    @Transactional
    public MedicationDto toggleMedicationReminder(UUID id) {
        CareRecord med = load(id);
        Map<String, Object> details = new HashMap<>(med.getDetails());
        Object cur = details.get("reminderEnabled");
        boolean enabled = cur instanceof Boolean b && b;
        details.put("reminderEnabled", !enabled);
        med.updateDetails(details);
        careRecordRepository.save(med);
        return CareRecordDtoMapper.toMedicationDto(med, careRecordRepository.findByParentRecordId(id));
    }

    @Transactional
    public String deleteMedication(UUID id) {
        CareRecord med = load(id);
        med.changeStatus(CareRecordStatus.CANCELLED);
        careRecordRepository.save(med);
        for (CareRecord child : careRecordRepository.findByParentRecordId(id)) {
            child.changeStatus(CareRecordStatus.CANCELLED);
            careRecordRepository.save(child);
        }
        return id.toString();
    }

    // --- 일정 --------------------------------------------------------------

    @Transactional
    public ScheduleDto createSchedule(CreateScheduleRequest req) {
        UUID seniorId = seniorId();
        Map<String, Object> details = new HashMap<>();
        put(details, "title", req.title());
        put(details, "startsAt", req.startsAt());
        put(details, "endsAt", req.endsAt());
        put(details, "location", req.location());
        put(details, "relatedPersonName", req.relatedPersonName());
        put(details, "description", req.description());
        put(details, "reminderEnabled", req.reminderEnabled());
        put(details, "reminderLeadMinutes", req.reminderLeadMinutes());
        put(details, "followUpEnabled", req.followUpEnabled());
        put(details, "followUpQuestion", req.followUpQuestion());

        String recordType = req.recordType() == null ? "PERSONAL_SCHEDULE" : req.recordType();
        // startsAt 이 곧 이 일정의 시간축 위 위치다. CareRecord.create 가 details 에서
        // 꺼내 occurred_at 에 넣는다 (S15P11E102-230).
        //
        // ★ 그래서 고쳐지는 버그: 현관 인사(GreetingDecider)는 "오늘 약속"을 찾을 때
        //   details.scheduledAt 을 읽었는데, 쓰는 쪽인 여기는 startsAt 을 넣었다.
        //   같은 뜻의 규약이 둘이었고 스키마가 둘을 맞춰줄 수 없었으므로, 어긋남이
        //   조용했다 — "오늘 약속 있으시죠" 인사가 한 번도 나간 적이 없다.
        CareRecord r = careRecordRepository.save(CareRecord.create(seniorId, recordType, details));
        return CareRecordDtoMapper.toScheduleDto(r);
    }

    @Transactional
    public ScheduleDto updateSchedule(UUID id, UpdateScheduleRequest req) {
        CareRecord r = load(id);
        Map<String, Object> details = new HashMap<>(r.getDetails());
        put(details, "title", req.title());
        put(details, "startsAt", req.startsAt());
        put(details, "endsAt", req.endsAt());
        put(details, "location", req.location());
        put(details, "relatedPersonName", req.relatedPersonName());
        put(details, "description", req.description());
        put(details, "reminderEnabled", req.reminderEnabled());
        put(details, "reminderLeadMinutes", req.reminderLeadMinutes());
        put(details, "followUpEnabled", req.followUpEnabled());
        put(details, "followUpQuestion", req.followUpQuestion());
        r.updateDetails(details);
        // 시작 시각을 바꾸면 시간축 위의 위치도 함께 옮긴다. 컬럼만 옛 시각으로 남으면
        // 대시보드는 새 시각을, 집계는 옛 시각을 말한다.
        r.occurredAt(CareRecordTime.fromDetails(details));

        if (req.status() != null) {
            r.changeStatus(mapScheduleStatus(req.status()));
        }
        careRecordRepository.save(r);
        return CareRecordDtoMapper.toScheduleDto(r);
    }

    // --- 공통 --------------------------------------------------------------

    private static Map<String, Object> dailyRecurrence(String localTime) {
        Map<String, Object> recurrence = new HashMap<>();
        recurrence.put("frequency", "DAILY");
        recurrence.put("times", List.of(localTime));
        return recurrence;
    }

    private static CareRecordStatus mapScheduleStatus(String feStatus) {
        return switch (feStatus) {
            case "COMPLETED" -> CareRecordStatus.COMPLETED;
            case "CANCELLED" -> CareRecordStatus.CANCELLED;
            default -> CareRecordStatus.ACTIVE; // UPCOMING
        };
    }

    private UUID seniorId() {
        return appUserRepository.findFirstByUserType(SENIOR_USER_TYPE)
                .orElseThrow(() -> new IllegalStateException("등록된 어르신이 없습니다."))
                .getId();
    }

    private CareRecord load(UUID id) {
        return careRecordRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "돌봄 기록을 찾을 수 없습니다: " + id));
    }

    private static void put(Map<String, Object> map, String key, Object value) {
        if (value != null) {
            map.put(key, value);
        }
    }
}
