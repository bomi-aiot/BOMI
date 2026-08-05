package com.ssafy.bomi.scenario.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.mqtt.outbound.RobotCommand;
import com.ssafy.bomi.mqtt.outbound.RobotCommandPublisher;
import com.ssafy.bomi.mqtt.outbound.RobotCommandType;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.scenario.config.MedicationReminderProperties;
import com.ssafy.bomi.scenario.domain.Scenario;
import com.ssafy.bomi.scenario.domain.ScenarioType;
import com.ssafy.bomi.scenario.repository.ScenarioRepository;
import java.time.Clock;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * 복약 알림 당번 검증. 시계를 고정해 "아침 8시"를 기다리지 않고 판정만 시험한다.
 * 시나리오: 혈압약, 매일 08:00, lead 10분, 유예 15분 → 알림 창 = 07:50 ~ 08:15.
 */
class MedicationReminderSchedulerTest {

    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

    private final CareRecordRepository careRecordRepository = mock(CareRecordRepository.class);
    private final ScenarioRepository scenarioRepository = mock(ScenarioRepository.class);
    private final RobotRepository robotRepository = mock(RobotRepository.class);
    private final RobotCommandPublisher commandPublisher = mock(RobotCommandPublisher.class);
    private final MedicationReminderProperties properties = new MedicationReminderProperties();

    private final UUID seniorId = UUID.randomUUID();
    private final UUID medicationId = UUID.randomUUID();
    private final UUID scheduleId = UUID.randomUUID();
    private final UUID robotUuid = UUID.randomUUID();

    private MedicationReminderScheduler schedulerAt(String isoLocalDateTime) {
        Clock fixed = Clock.fixed(
            ZonedDateTime.of(java.time.LocalDateTime.parse(isoLocalDateTime), KST).toInstant(), KST);
        MedicationReminderScheduler scheduler = new MedicationReminderScheduler(
            careRecordRepository, scenarioRepository, robotRepository, commandPublisher,
            new ScenarioStartGuard(scenarioRepository), properties, fixed);

        when(scenarioRepository.save(any(Scenario.class))).thenAnswer(invocation -> {
            Scenario s = invocation.getArgument(0);
            if (s.getId() == null) {
                ReflectionTestUtils.setField(s, "id", UUID.randomUUID());
            }
            return s;
        });
        return scheduler;
    }

    /** 혈압약(부모, reminderEnabled) + 매일 08:00 스케줄(자식, lead 10분) 시드. */
    private void seedMedication(boolean reminderEnabled) {
        Map<String, Object> medDetails = new HashMap<>();
        medDetails.put("medicationName", "혈압약");
        medDetails.put("reminderEnabled", reminderEnabled);
        CareRecord medication = CareRecord.create(seniorId, "MEDICATION", medDetails);
        ReflectionTestUtils.setField(medication, "id", medicationId);

        Map<String, Object> schedDetails = new HashMap<>();
        schedDetails.put("medicationName", "혈압약");
        schedDetails.put("localTimes", List.of("08:00"));
        schedDetails.put("timeZone", "Asia/Seoul");
        schedDetails.put("reminderLeadMinutes", 10);
        CareRecord schedule = CareRecord.create(seniorId, "MEDICATION_SCHEDULE", schedDetails);
        ReflectionTestUtils.setField(schedule, "id", scheduleId);
        schedule.assignParent(medicationId);

        when(careRecordRepository.findByRecordTypeAndStatus("MEDICATION_SCHEDULE", CareRecordStatus.ACTIVE))
            .thenReturn(List.of(schedule));
        when(careRecordRepository.findById(medicationId)).thenReturn(Optional.of(medication));

        Robot robot = Robot.create(seniorId, "robot-01");
        ReflectionTestUtils.setField(robot, "id", robotUuid);
        when(robotRepository.findBySeniorId(seniorId)).thenReturn(Optional.of(robot));
    }

    @Test
    void insideWindowStartsScenarioWithNavigateAndSpeak() {
        seedMedication(true);

        schedulerAt("2026-08-05T07:55:00").tick(); // 창(07:50~08:15) 안

        ArgumentCaptor<Scenario> scenarioCaptor = ArgumentCaptor.forClass(Scenario.class);
        verify(scenarioRepository).save(scenarioCaptor.capture());
        assertThat(scenarioCaptor.getValue().getScenarioType()).isEqualTo(ScenarioType.MEDICATION_REMINDER);
        assertThat(scenarioCaptor.getValue().getExternalEventId())
            .isEqualTo("med-%s-2026-08-05-08:00".formatted(scheduleId));

        ArgumentCaptor<RobotCommand> commandCaptor = ArgumentCaptor.forClass(RobotCommand.class);
        verify(commandPublisher, times(2)).publish(commandCaptor.capture());
        RobotCommand navigate = commandCaptor.getAllValues().get(0);
        assertThat(navigate.type()).isEqualTo(RobotCommandType.NAVIGATE);
        assertThat(navigate.payload()).containsEntry("target", "LIVING_ROOM");
        assertThat(scenarioCaptor.getValue().getActiveNavigationCommandId())
            .isEqualTo(navigate.commandId());
        RobotCommand speak = commandCaptor.getAllValues().get(1);
        assertThat(speak.type()).isEqualTo(RobotCommandType.SPEAK);
        assertThat((String) speak.payload().get("text")).contains("혈압약");
    }

    @Test
    void beforeWindowStaysSilent() {
        seedMedication(true);

        schedulerAt("2026-08-05T07:49:00").tick(); // lead 10분 → 창은 07:50부터

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void afterGraceStaysSilent() {
        seedMedication(true);

        schedulerAt("2026-08-05T08:16:00").tick(); // 유예 15분 → 창은 08:15 미만까지

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void alreadyRemindedSlotIsSkipped() {
        // 재시작 안전성의 핵심: 판정이 메모리가 아니라 DB(슬롯 키)다.
        seedMedication(true);
        when(scenarioRepository.existsByScenarioTypeAndExternalEventId(
            eq(ScenarioType.MEDICATION_REMINDER), any())).thenReturn(true);

        schedulerAt("2026-08-05T07:55:00").tick();

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void reminderDisabledOnParentStaysSilent() {
        seedMedication(false);

        schedulerAt("2026-08-05T07:55:00").tick();

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void activeScenarioDefersToNextTick() {
        // 창 안이지만 다른 시나리오 진행 중 → 이번 틱 포기 (다음 틱이 재시도)
        seedMedication(true);
        when(scenarioRepository.existsBySeniorIdAndFinalStatusIn(eq(seniorId), anyCollection()))
            .thenReturn(true);

        schedulerAt("2026-08-05T07:55:00").tick();

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }

    @Test
    void missingRobotIsDroppedWithoutThrowing() {
        seedMedication(true);
        when(robotRepository.findBySeniorId(seniorId)).thenReturn(Optional.empty());

        schedulerAt("2026-08-05T07:55:00").tick(); // must not throw

        verify(scenarioRepository, never()).save(any());
        verifyNoInteractions(commandPublisher);
    }
}
