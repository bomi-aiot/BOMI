package com.ssafy.bomi.scenario.application;

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
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 복약 알림 당번 (시나리오 ②): 1분마다 깨어나 "지금 알려야 할 약이 있나"를 묻는다.
 *
 * <p>이 시나리오만 트리거가 센서가 아닌 시간이다. 알람을 슬롯별로 예약하는 대신
 * 매분 폴링하는 이유: 예약은 메모리에 살아서 재시작·수정·삭제마다 재조정이 필요하지만,
 * 폴링은 매번 DB 의 최신 상태를 새로 보므로 그 문제들이 통째로 없다. 폴링 비용은
 * 인덱스 조회 한 번이다.</p>
 *
 * <p>세 가지 안전장치:</p>
 * <ul>
 *   <li><b>슬롯 키</b> — {@code med-{스케줄ID}-{날짜}-{시각}} 을 시나리오의
 *       {@code external_event_id} 에 저장한다. 시나리오 생성 자체가 알림 이력이 되어
 *       백엔드가 재시작해도 같은 슬롯을 두 번 알리지 못한다.</li>
 *   <li><b>알림 창</b> — [예정-lead분, 예정+유예분] 밖이면 침묵. 창 안에서 문지기에게
 *       막히면 이번 틱은 포기하고 다음 틱(1분 뒤)이 자연스럽게 재시도한다.</li>
 *   <li><b>문지기</b> — {@link ScenarioStartGuard} 활성 검사만 쓴다(쿨다운 ZERO).
 *       중복 방지는 슬롯 키가 이미 완전하게 하고, 쿨다운을 걸면 "아침약 완료 30분 안에
 *       점심약 도래" 같은 정상 케이스를 막는다.</li>
 * </ul>
 *
 * <p>시작 이후(도착→대화→복귀→완료)는 기존 시나리오 처리 로직이 타입 무관으로 끌고
 * 간다 — {@link WellnessCheckOrchestrator}와 같은 원리.</p>
 */
@Component
@ConditionalOnProperty(prefix = "bomi.mqtt", name = "enabled", havingValue = "true")
public class MedicationReminderScheduler {

    private static final Logger log = LoggerFactory.getLogger(MedicationReminderScheduler.class);
    private static final Duration COMMAND_TTL = Duration.ofMinutes(2);
    private static final String RECORD_MEDICATION_SCHEDULE = "MEDICATION_SCHEDULE";
    private static final ZoneId DEFAULT_ZONE = ZoneId.of("Asia/Seoul");

    private final CareRecordRepository careRecordRepository;
    private final ScenarioRepository scenarioRepository;
    private final RobotRepository robotRepository;
    private final RobotCommandPublisher commandPublisher;
    private final ScenarioStartGuard startGuard;
    private final MedicationReminderProperties properties;
    private final Clock clock;

    public MedicationReminderScheduler(
        CareRecordRepository careRecordRepository,
        ScenarioRepository scenarioRepository,
        RobotRepository robotRepository,
        RobotCommandPublisher commandPublisher,
        ScenarioStartGuard startGuard,
        MedicationReminderProperties properties,
        Clock clock
    ) {
        this.careRecordRepository = careRecordRepository;
        this.scenarioRepository = scenarioRepository;
        this.robotRepository = robotRepository;
        this.commandPublisher = commandPublisher;
        this.startGuard = startGuard;
        this.properties = properties;
        this.clock = clock;
    }

    /** 1분 주기 틱. 예외가 새어 나가면 다음 틱이 조용히 죽으므로 전체를 감싼다. */
    @Scheduled(fixedDelay = 60_000)
    @Transactional
    public void tick() {
        try {
            List<CareRecord> schedules = careRecordRepository
                .findByRecordTypeAndStatus(RECORD_MEDICATION_SCHEDULE, CareRecordStatus.ACTIVE);
            for (CareRecord schedule : schedules) {
                remindIfDue(schedule);
            }
        } catch (RuntimeException ex) {
            // 틱 하나의 실패가 스케줄링 자체를 멈추면 안 된다. 기록하고 다음 틱에 맡긴다.
            log.error("Medication reminder tick failed; will retry next tick", ex);
        }
    }

    private void remindIfDue(CareRecord schedule) {
        if (!reminderEnabledOnParent(schedule)) {
            return;
        }

        Map<String, Object> details = schedule.getDetails();
        ZoneId zone = zoneOf(details);
        ZonedDateTime now = ZonedDateTime.now(clock).withZoneSameInstant(zone);
        long leadMinutes = longValue(details.get("reminderLeadMinutes"), 0);

        for (String timeText : localTimes(details)) {
            LocalTime slotTime = parseTimeOrNull(timeText);
            if (slotTime == null) {
                log.warn("Unparseable medication time; skipping slot: scheduleId={}, time={}",
                    schedule.getId(), timeText);
                continue;
            }
            // 오늘 날짜의 슬롯만 본다. 자정을 걸치는 창(예: 00:05 약의 lead 10분)은
            // 창의 앞부분이 잘리는 정도로 단순화한다 — 폴링이 매분이라 실사용 영향 없음.
            LocalDate today = now.toLocalDate();
            ZonedDateTime slot = today.atTime(slotTime).atZone(zone);
            ZonedDateTime windowStart = slot.minusMinutes(leadMinutes);
            ZonedDateTime windowEnd = slot.plusMinutes(properties.getGraceMinutes());
            if (now.isBefore(windowStart) || !now.isBefore(windowEnd)) {
                continue;
            }

            String slotKey = "med-%s-%s-%s".formatted(schedule.getId(), today, slotTime);
            if (scenarioRepository.existsByScenarioTypeAndExternalEventId(
                    ScenarioType.MEDICATION_REMINDER, slotKey)) {
                continue; // 오늘 이 슬롯은 이미 알렸다 (재시작에도 안전한 DB 판정)
            }
            startReminder(schedule, slotKey);
        }
    }

    private void startReminder(CareRecord schedule, String slotKey) {
        UUID seniorId = schedule.getSeniorId();
        var blocked = startGuard.check(seniorId, ScenarioType.MEDICATION_REMINDER, Duration.ZERO);
        if (blocked.isPresent()) {
            // 창이 열려 있는 동안 다음 틱이 재시도한다. 큐가 필요 없는 이유.
            log.info("Medication reminder deferred ({}): seniorId={}, slot={}",
                blocked.get(), seniorId, slotKey);
            return;
        }
        Robot robot = robotRepository.findBySeniorId(seniorId).orElse(null);
        if (robot == null) {
            log.warn("No robot assigned to senior; dropping medication reminder: seniorId={}", seniorId);
            return;
        }

        Scenario scenario = Scenario.create(
            seniorId, robot.getId(), ScenarioType.MEDICATION_REMINDER, slotKey);
        scenario.beginMovingToEntrance(); // "시나리오 목적지로 이동 중"의 범용 의미
        String navigationCommandId = UUID.randomUUID().toString();
        scenario.expectNavigationResult(
            navigationCommandId, HomecomingContract.TARGET_LIVING_ROOM);
        scenarioRepository.save(scenario);
        robot.changeMode(RobotModePolicy.forScenario(scenario.getFinalStatus()));
        robotRepository.save(robot);

        publish(navigationCommandId, scenario.getId(), robot, RobotCommandType.NAVIGATE,
            Map.of(HomecomingContract.NAV_TARGET_KEY, HomecomingContract.TARGET_LIVING_ROOM));
        publish(UUID.randomUUID().toString(), scenario.getId(), robot, RobotCommandType.SPEAK,
            Map.of(HomecomingContract.SPEAK_TEXT_KEY, speakText(schedule)));

        log.info("Medication reminder started: scenarioId={}, seniorId={}, slot={}",
            scenario.getId(), seniorId, slotKey);
    }

    // --- 데이터 해석 헬퍼 (details 는 스키마가 강제되지 않는 jsonb 라 방어적으로) ----

    /** reminderEnabled 는 부모 MEDICATION 기록에 있다. 부모가 없거나 비활성이면 알리지 않는다. */
    private boolean reminderEnabledOnParent(CareRecord schedule) {
        UUID parentId = schedule.getParentRecordId();
        if (parentId == null) {
            return false;
        }
        CareRecord parent = careRecordRepository.findById(parentId).orElse(null);
        if (parent == null || parent.getStatus() != CareRecordStatus.ACTIVE) {
            return false;
        }
        Object enabled = parent.getDetails().get("reminderEnabled");
        return Boolean.TRUE.equals(enabled) || "true".equalsIgnoreCase(String.valueOf(enabled));
    }

    private List<String> localTimes(Map<String, Object> details) {
        Object value = details.get("localTimes");
        if (value instanceof List<?> list) {
            return list.stream().map(String::valueOf).toList();
        }
        return List.of();
    }

    private ZoneId zoneOf(Map<String, Object> details) {
        Object tz = details.get("timeZone");
        if (tz instanceof String text && !text.isBlank()) {
            try {
                return ZoneId.of(text);
            } catch (RuntimeException ignored) {
                // 잘못된 타임존은 기본값으로 — 알림을 통째로 잃는 것보다 낫다.
            }
        }
        return DEFAULT_ZONE;
    }

    private LocalTime parseTimeOrNull(String text) {
        try {
            return LocalTime.parse(text);
        } catch (DateTimeParseException ex) {
            return null;
        }
    }

    private long longValue(Object value, long fallback) {
        if (value instanceof Number number) {
            return number.longValue();
        }
        if (value instanceof String text) {
            try {
                return Long.parseLong(text.trim());
            } catch (NumberFormatException ignored) {
                // fall through
            }
        }
        return fallback;
    }

    private String speakText(CareRecord schedule) {
        Object name = schedule.getDetails().get("medicationName");
        String medication = (name instanceof String text && !text.isBlank()) ? text : "약";
        return "어르신, %s 드실 시간이에요.".formatted(medication);
    }

    private void publish(
        String commandId,
        UUID scenarioId,
        Robot robot,
        RobotCommandType type,
        Map<String, Object> payload
    ) {
        if (robot.getDeviceId() == null) {
            throw new IllegalStateException("Robot has no deviceId; cannot address command: " + robot.getId());
        }
        OffsetDateTime now = OffsetDateTime.now(clock);
        commandPublisher.publish(new RobotCommand(
            commandId, scenarioId, robot.getDeviceId(),
            type, now, now.plus(COMMAND_TTL), payload));
    }
}
