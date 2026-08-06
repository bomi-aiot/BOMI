package com.ssafy.bomi.care.web;

import com.ssafy.bomi.care.web.dto.MedicationDto;
import com.ssafy.bomi.care.web.dto.MedicationRequests.CreateMedicationRequest;
import com.ssafy.bomi.care.web.dto.MedicationRequests.UpdateMedicationRequest;
import com.ssafy.bomi.care.web.dto.MedicationResponseDto;
import com.ssafy.bomi.care.web.dto.ScheduleDto;
import com.ssafy.bomi.care.web.dto.ScheduleRequests.CreateScheduleRequest;
import com.ssafy.bomi.care.web.dto.ScheduleRequests.UpdateScheduleRequest;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 가디언 웹 돌봄기록 API (일정·복약) — 조회 + 쓰기. 단일 어르신 전제(P0)라 경로에 elderId 없음.
 * 접두: {@code /api/v1/care-records} (FE API_ENDPOINTS 와 일치).
 */
@RestController
@RequestMapping("/api/v1/care-records")
@Tag(name = "Guardian Care Record", description = "돌봄기록 일정·복약 — 가디언웹이 호출합니다.")
public class CareRecordController {

    private final CareRecordQueryService queryService;
    private final CareRecordCommandService commandService;

    public CareRecordController(
            CareRecordQueryService queryService, CareRecordCommandService commandService) {
        this.queryService = queryService;
        this.commandService = commandService;
    }

    // --- 조회 ---

    @GetMapping("/schedules")
    public List<ScheduleDto> getSchedules() {
        return queryService.getSchedules();
    }

    @GetMapping("/medications")
    public List<MedicationDto> getMedications() {
        return queryService.getMedications();
    }

    @GetMapping("/medication-responses")
    public List<MedicationResponseDto> getMedicationResponses() {
        return queryService.getTodayMedicationResponses();
    }

    // --- 복약 쓰기 ---

    @PostMapping("/medications")
    public MedicationDto createMedication(@RequestBody CreateMedicationRequest request) {
        return commandService.createMedication(request);
    }

    @PutMapping("/medications/{id}")
    public MedicationDto updateMedication(
            @PathVariable UUID id, @RequestBody UpdateMedicationRequest request) {
        return commandService.updateMedication(id, request);
    }

    @PostMapping("/medications/{id}/toggle-status")
    public MedicationDto toggleMedicationStatus(@PathVariable UUID id) {
        return commandService.toggleMedicationStatus(id);
    }

    @PostMapping("/medications/{id}/toggle-reminder")
    public MedicationDto toggleMedicationReminder(@PathVariable UUID id) {
        return commandService.toggleMedicationReminder(id);
    }

    @DeleteMapping("/medications/{id}")
    public Map<String, String> deleteMedication(@PathVariable UUID id) {
        return Map.of("id", commandService.deleteMedication(id));
    }

    // --- 일정 쓰기 ---

    @PostMapping("/schedules")
    public ScheduleDto createSchedule(@RequestBody CreateScheduleRequest request) {
        return commandService.createSchedule(request);
    }

    @PutMapping("/schedules/{id}")
    public ScheduleDto updateSchedule(
            @PathVariable UUID id, @RequestBody UpdateScheduleRequest request) {
        return commandService.updateSchedule(id, request);
    }
}
