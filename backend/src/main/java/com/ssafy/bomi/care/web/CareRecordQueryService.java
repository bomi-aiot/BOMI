package com.ssafy.bomi.care.web;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.care.web.dto.MedicationDto;
import com.ssafy.bomi.care.web.dto.MedicationDto.MedicationScheduleDto;
import com.ssafy.bomi.care.web.dto.MedicationResponseDto;
import com.ssafy.bomi.care.web.dto.ScheduleDto;
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
 * 돌봄 기록(care_record) 조회 서비스 — 일정 / 복약 / 복약 응답. 단일 어르신 전제(P0).
 * care_record 는 시간 컬럼이 없어 시각·수치는 details(jsonb)에서 읽는다(계약 §1).
 */
@Service
public class CareRecordQueryService {

    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
    private static final String SENIOR_USER_TYPE = "SENIOR";
    private static final Set<String> SCHEDULE_TYPES = Set.of("APPOINTMENT", "PERSONAL_SCHEDULE");

    private final AppUserRepository appUserRepository;
    private final CareRecordRepository careRecordRepository;

    public CareRecordQueryService(
            AppUserRepository appUserRepository, CareRecordRepository careRecordRepository) {
        this.appUserRepository = appUserRepository;
        this.careRecordRepository = careRecordRepository;
    }

    // --- 일정 --------------------------------------------------------------

    @Transactional(readOnly = true)
    public List<ScheduleDto> getSchedules() {
        List<ScheduleDto> result = new ArrayList<>();
        for (CareRecord r : records()) {
            if (!SCHEDULE_TYPES.contains(r.getRecordType())
                    || r.getStatus() == CareRecordStatus.SUPERSEDED) {
                continue;
            }
            result.add(toScheduleDto(r));
        }
        result.sort(Comparator.comparing(
                (ScheduleDto s) -> parseDateTime(s.startsAt()),
                Comparator.nullsLast(Comparator.naturalOrder())));
        return result;
    }

    private ScheduleDto toScheduleDto(CareRecord r) {
        Map<String, Object> d = r.getDetails();
        return new ScheduleDto(
                r.getId().toString(),
                r.getRecordType(),
                r.getStatus().name(),
                str(d, "title"),
                str(d, "startsAt"),
                str(d, "endsAt"),
                str(d, "location"),
                str(d, "relatedPersonName"),
                str(d, "description"),
                bool(d, "reminderEnabled"),
                intVal(d, "reminderLeadMinutes"),
                bool(d, "followUpEnabled"),
                str(d, "followUpQuestion"));
    }

    // --- 복약 --------------------------------------------------------------

    @Transactional(readOnly = true)
    public List<MedicationDto> getMedications() {
        List<CareRecord> all = records();
        List<CareRecord> schedules = all.stream()
                .filter(r -> "MEDICATION_SCHEDULE".equals(r.getRecordType()))
                .toList();
        List<MedicationDto> result = new ArrayList<>();
        for (CareRecord m : all) {
            if (!"MEDICATION".equals(m.getRecordType())
                    || m.getStatus() == CareRecordStatus.SUPERSEDED) {
                continue;
            }
            result.add(toMedicationDto(m, schedules));
        }
        return result;
    }

    private MedicationDto toMedicationDto(CareRecord m, List<CareRecord> schedules) {
        Map<String, Object> d = m.getDetails();
        List<MedicationScheduleDto> childSchedules = schedules.stream()
                .filter(s -> m.getId().equals(s.getParentRecordId()))
                .map(s -> toMedicationScheduleDto(s, m.getId()))
                .toList();
        return new MedicationDto(
                m.getId().toString(),
                m.getRecordType(),
                m.getStatus().name(),
                str(d, "medicationName"),
                numStr(d, "dose"),
                str(d, "doseUnit"),
                str(d, "instruction"),
                str(d, "purpose"),
                str(d, "activeIngredient"),
                str(d, "startedOn"),
                str(d, "endedOn"),
                bool(d, "reminderEnabled"),
                childSchedules);
    }

    private MedicationScheduleDto toMedicationScheduleDto(CareRecord s, UUID medicationId) {
        Map<String, Object> d = s.getDetails();
        Map<String, Object> recurrence = s.getRecurrence();
        return new MedicationScheduleDto(
                s.getId().toString(),
                medicationId.toString(),
                recurrence == null ? null : str(recurrence, "frequency"),
                str(d, "timeZone"),
                stringList(d, "localTimes"),
                intVal(d, "reminderLeadMinutes"),
                s.getStatus() == CareRecordStatus.ACTIVE);
    }

    // --- 복약 응답 (오늘) --------------------------------------------------
    // 스케줄의 오늘 복용 시각을 펼치고 복용 기록(MEDICATION_TAKEN)과 매칭한다.

    @Transactional(readOnly = true)
    public List<MedicationResponseDto> getTodayMedicationResponses() {
        LocalDate today = LocalDate.now(SEOUL);
        OffsetDateTime now = OffsetDateTime.now();
        List<CareRecord> all = records();
        List<CareRecord> schedules = all.stream()
                .filter(r -> r.getStatus() == CareRecordStatus.ACTIVE)
                .filter(r -> "MEDICATION_SCHEDULE".equals(r.getRecordType()))
                .toList();
        List<CareRecord> taken = all.stream()
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
                result.add(toResponse(schedule, medicationName, scheduledAt, match, now));
            }
        }
        result.sort(Comparator.comparing(
                (MedicationResponseDto r) -> parseDateTime(r.scheduledAt()),
                Comparator.nullsLast(Comparator.naturalOrder())));
        return result;
    }

    private MedicationResponseDto toResponse(
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
                    id, medicationId, scheduleId, iso(scheduledAt),
                    str(td, "respondedAt"), declined ? "DECLINED" : "CONFIRMED", str(td, "responseText"));
        }
        String status = scheduledAt.isAfter(now) ? "UPCOMING" : "MISSED";
        String responseText = medicationName == null ? null : medicationName + " 복약 알림";
        return new MedicationResponseDto(id, medicationId, scheduleId, iso(scheduledAt), null, status, responseText);
    }

    /**
     * 이 복약 슬롯에 해당하는 복용 기록을 찾는다.
     *
     * <p>occurred_at 으로 맞춘다 (S15P11E102-230). 대시보드(DashboardService)와 같은
     * 규칙이어야 한다 — 두 화면이 같은 약에 대해 다른 상태를 말하면 안 된다.</p>
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

    // --- 공통 --------------------------------------------------------------

    private List<CareRecord> records() {
        UUID seniorId = appUserRepository.findFirstByUserType(SENIOR_USER_TYPE)
                .orElseThrow(() -> new IllegalStateException("등록된 어르신이 없습니다."))
                .getId();
        return careRecordRepository.findBySeniorId(seniorId);
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

    private static List<String> stringList(Map<String, Object> map, String key) {
        if (map == null) {
            return List.of();
        }
        Object v = map.get(key);
        if (v instanceof List<?> list) {
            return list.stream().filter(o -> o != null).map(Object::toString).toList();
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

    private static String numStr(Map<String, Object> map, String key) {
        Object v = map == null ? null : map.get(key);
        if (v == null) {
            return null;
        }
        if (v instanceof Number n) {
            double dbl = n.doubleValue();
            if (dbl == Math.floor(dbl) && !Double.isInfinite(dbl)) {
                return String.valueOf((long) dbl);
            }
            return String.valueOf(dbl);
        }
        return v.toString();
    }

    private static Boolean bool(Map<String, Object> map, String key) {
        Object v = map == null ? null : map.get(key);
        if (v == null) {
            return null;
        }
        if (v instanceof Boolean b) {
            return b;
        }
        return Boolean.parseBoolean(v.toString());
    }

    private static Integer intVal(Map<String, Object> map, String key) {
        Object v = map == null ? null : map.get(key);
        if (v == null) {
            return null;
        }
        if (v instanceof Number n) {
            return n.intValue();
        }
        try {
            return Integer.parseInt(v.toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String iso(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }
}
