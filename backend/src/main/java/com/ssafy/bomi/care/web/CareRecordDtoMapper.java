package com.ssafy.bomi.care.web;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.web.dto.MedicationDto;
import com.ssafy.bomi.care.web.dto.MedicationDto.MedicationScheduleDto;
import com.ssafy.bomi.care.web.dto.ScheduleDto;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * care_record → 응답 DTO 정적 매퍼. 쓰기(CareRecordCommandService)가 생성 결과를 그대로 반환할 때 사용.
 * (조회 서비스 CareRecordQueryService 는 자체 매핑을 유지 — 추후 이 매퍼로 통합 가능.)
 */
final class CareRecordDtoMapper {

    private CareRecordDtoMapper() {
    }

    static ScheduleDto toScheduleDto(CareRecord r) {
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

    static MedicationDto toMedicationDto(CareRecord m, List<CareRecord> schedules) {
        Map<String, Object> d = m.getDetails();
        List<MedicationScheduleDto> children = schedules.stream()
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
                children);
    }

    static MedicationScheduleDto toMedicationScheduleDto(CareRecord s, UUID medicationId) {
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

    // --- helpers ---

    static List<String> stringList(Map<String, Object> map, String key) {
        if (map == null) {
            return List.of();
        }
        Object v = map.get(key);
        if (v instanceof List<?> list) {
            return list.stream().filter(o -> o != null).map(Object::toString).toList();
        }
        return List.of();
    }

    static String str(Map<String, Object> map, String key) {
        Object v = map == null ? null : map.get(key);
        return v == null ? null : v.toString();
    }

    static String numStr(Map<String, Object> map, String key) {
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

    static Boolean bool(Map<String, Object> map, String key) {
        Object v = map == null ? null : map.get(key);
        if (v == null) {
            return null;
        }
        if (v instanceof Boolean b) {
            return b;
        }
        return Boolean.parseBoolean(v.toString());
    }

    static Integer intVal(Map<String, Object> map, String key) {
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
}
