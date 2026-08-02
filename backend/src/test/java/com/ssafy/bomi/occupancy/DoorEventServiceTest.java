package com.ssafy.bomi.occupancy;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.occupancy.application.DoorEventService;
import com.ssafy.bomi.occupancy.application.DoorEventService.DoorEventOutcome;
import com.ssafy.bomi.occupancy.application.EntranceDirectionResolver.Signal;
import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import com.ssafy.bomi.occupancy.repository.OccupancyEventRepository;
import com.ssafy.bomi.robot.domain.OccupancyStatus;
import com.ssafy.bomi.robot.domain.Robot;
import com.ssafy.bomi.robot.repository.RobotRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Transactional;

/**
 * 현관 판정과 인사 — S15P11E102-226 완료 조건.
 *
 * <p>검증하는 것</p>
 * <ol>
 *   <li>두 센서 순서로 IN/OUT 판정, 판정 불가면 UNKNOWN</li>
 *   <li>짧은 IN-OUT 쌍(배달)에 인사가 나가지 않음</li>
 *   <li>방향별 인사가 하나만</li>
 *   <li>확정 occupancy 가 robot 에 반영되고 occupancy_event 에 적재됨</li>
 * </ol>
 *
 * <p>MQTT 는 꺼져 있으므로 실제 발화 명령은 나가지 않는다. 결정은 응답으로 확인한다 —
 * 그 분리 자체가 의도된 동작이고, 브로커 없는 환경에서도 재실 반영은 살아 있어야 한다.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false",
        "bomi.entrance.correlation-window=15s",
        "bomi.entrance.reversal-window=30s",
        "bomi.entrance.greeting-ttl=45s"
    })
@Transactional
class DoorEventServiceTest {

    private static EmbeddedPostgres postgres;

    @Autowired private DoorEventService service;
    @Autowired private OccupancyEventRepository occupancyEventRepository;
    @Autowired private RobotRepository robotRepository;
    @Autowired private CareRecordRepository careRecordRepository;
    @Autowired private AppUserRepository appUserRepository;

    private UUID seniorId;

    @BeforeAll
    static void startPostgres() throws IOException {
        postgres = EmbeddedPostgres.start();
    }

    @AfterAll
    static void stopPostgres() throws IOException {
        if (postgres != null) {
            postgres.close();
        }
    }

    @DynamicPropertySource
    static void datasourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> postgres.getJdbcUrl("postgres", "postgres"));
        registry.add("spring.datasource.username", () -> "postgres");
        registry.add("spring.datasource.password", () -> "");
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
    }

    @BeforeEach
    void setUpSenior() {
        AppUser senior = appUserRepository.save(AppUser.create("SENIOR", "김순자", null, "순자님"));
        seniorId = senior.getId();
        robotRepository.save(Robot.create(seniorId, "robot-" + UUID.randomUUID()));
    }

    // ── 완료 조건 1: 두 센서 순서로 판정 ─────────────────────────────────────

    @Test
    void comingHomeConfirmsOccupancyAndGreets() {
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.DOOR_OPENED, now, null);

        DoorEventOutcome outcome = service.accept(seniorId, Signal.MOTION, now.plusSeconds(3), null);

        assertThat(outcome.resolved()).isTrue();
        assertThat(outcome.direction()).isEqualTo(OccupancyDirection.IN);
        assertThat(outcome.occupancy()).isEqualTo(OccupancyStatus.HOME);
        assertThat(outcome.greeting()).isNotBlank();
    }

    @Test
    void goingOutConfirmsAwayAndSeesThemOff() {
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.MOTION, now, null);

        DoorEventOutcome outcome = service.accept(
            seniorId, Signal.DOOR_OPENED, now.plusSeconds(3), null);

        assertThat(outcome.direction()).isEqualTo(OccupancyDirection.OUT);
        assertThat(outcome.occupancy()).isEqualTo(OccupancyStatus.AWAY);
        assertThat(outcome.greeting()).isNotBlank();
    }

    @Test
    void anIncompletePassageChangesNothing() {
        /*
         * ★ 문만 열리고 아무도 지나가지 않았다. 재실 상태를 건드리면 안 된다.
         */
        OffsetDateTime now = OffsetDateTime.now();

        DoorEventOutcome outcome = service.accept(seniorId, Signal.DOOR_OPENED, now, null);

        assertThat(outcome.resolved()).isFalse();
        assertThat(outcome.greeting()).isNull();
        assertThat(robot().getOccupancyStatus()).isEqualTo(OccupancyStatus.UNKNOWN);
        assertThat(occupancyEventRepository.findAll()).isEmpty();
    }

    // ── 완료 조건 2: 짧은 IN-OUT 쌍에 인사가 나가지 않는다 ───────────────────

    @Test
    void aReversalWithinTheWindowIsTreatedAsAContradiction() {
        /*
         * ★★ 배달이 정확히 이 모양이다. 문 앞으로 걸어가 문이 열리고, 잠시 뒤
         * 패턴이 거꾸로 돈다.
         *
         * 두 판정을 다 믿으면 재실 상태가 두 번 뒤집히고, 아무 데도 안 가신 어르신께
         * "다녀오세요"가 나간다. 모순일 때는 더 그럴듯한 쪽을 고르지 않고 UNKNOWN 이다.
         */
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.MOTION, now, null);
        service.accept(seniorId, Signal.DOOR_OPENED, now.plusSeconds(2), null);  // OUT

        service.accept(seniorId, Signal.DOOR_OPENED, now.plusSeconds(5), null);
        DoorEventOutcome reversal = service.accept(
            seniorId, Signal.MOTION, now.plusSeconds(7), null);                  // IN, 너무 빠르다

        assertThat(reversal.occupancy()).isEqualTo(OccupancyStatus.UNKNOWN);
        assertThat(reversal.greeting()).isNull();
        assertThat(robot().getOccupancyStatus()).isEqualTo(OccupancyStatus.UNKNOWN);
    }

    @Test
    void aGenuineReturnAfterTheWindowIsBelieved() {
        /*
         * 진짜 외출과 귀가는 창보다 오래 걸린다. 그것까지 모순으로 처리하면
         * 어르신은 영원히 UNKNOWN 이 된다.
         */
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.MOTION, now, null);
        service.accept(seniorId, Signal.DOOR_OPENED, now.plusSeconds(2), null);  // OUT

        OffsetDateTime later = now.plusMinutes(40);
        service.accept(seniorId, Signal.DOOR_OPENED, later, null);
        DoorEventOutcome back = service.accept(seniorId, Signal.MOTION, later.plusSeconds(3), null);

        assertThat(back.direction()).isEqualTo(OccupancyDirection.IN);
        assertThat(back.occupancy()).isEqualTo(OccupancyStatus.HOME);
    }

    // ── 완료 조건 3: 인사는 하나만 ───────────────────────────────────────────

    @Test
    void theEscortGreetingMentionsMedicationWhenNoneWasTakenToday() {
        /*
         * 나가시기 전이 마지막 기회다. 돌아오신 뒤에 묻는 것은 이미 늦은 경우가 많다.
         */
        careRecordRepository.save(CareRecord.create(seniorId, "MEDICATION_SCHEDULE",
            Map.of("medicationName", "혈압약")));
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.MOTION, now, null);

        DoorEventOutcome outcome = service.accept(
            seniorId, Signal.DOOR_OPENED, now.plusSeconds(2), null);

        assertThat(outcome.greeting()).contains("약");
    }

    @Test
    void theEscortGreetingDropsMedicationOnceItWasTaken() {
        careRecordRepository.save(CareRecord.create(seniorId, "MEDICATION_SCHEDULE",
            Map.of("medicationName", "혈압약")));
        careRecordRepository.save(CareRecord.create(seniorId, "MEDICATION_TAKEN",
            Map.of("scheduledAt", OffsetDateTime.now().toString(), "medicationName", "혈압약")));
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.MOTION, now, null);

        DoorEventOutcome outcome = service.accept(
            seniorId, Signal.DOOR_OPENED, now.plusSeconds(2), null);

        assertThat(outcome.greeting()).doesNotContain("약");
    }

    @Test
    void theGreetingIsOneSentence() {
        /*
         * ★ 현관은 실용 정보의 가치가 가장 높은 순간이고, 그래서 세 가지를 쏟고 싶어지는
         * 지점이다. 어르신은 이미 반쯤 나가 있다 (CLAUDE.md §14).
         */
        careRecordRepository.save(CareRecord.create(seniorId, "MEDICATION_SCHEDULE",
            Map.of("medicationName", "혈압약")));
        careRecordRepository.save(CareRecord.create(seniorId, "APPOINTMENT",
            Map.of("scheduledAt", OffsetDateTime.now().toString(), "title", "병원")));
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.MOTION, now, null);

        String greeting = service.accept(
            seniorId, Signal.DOOR_OPENED, now.plusSeconds(2), null).greeting();

        // 마침표·물음표로 끝나는 문장이 둘을 넘지 않는다.
        long sentences = greeting.chars().filter(c -> c == '.' || c == '?' || c == '!').count();
        assertThat(sentences).isLessThanOrEqualTo(2);
        assertThat(greeting).doesNotContain("병원");
    }

    @Test
    void aLateGreetingIsDroppedRatherThanAnnouncedToAnEmptyHallway() {
        /*
         * ★ 문이 열린 지 10분 뒤의 "어서오세요"는 침묵보다 나쁘다.
         *   만료된 인사는 재스케줄이 아니라 폐기다 (CLAUDE.md §11).
         */
        OffsetDateTime longAgo = OffsetDateTime.now().minusMinutes(10);
        service.accept(seniorId, Signal.DOOR_OPENED, longAgo, null);

        DoorEventOutcome outcome = service.accept(
            seniorId, Signal.MOTION, longAgo.plusSeconds(3), null);

        assertThat(outcome.direction()).isEqualTo(OccupancyDirection.IN);
        // 재실은 여전히 반영된다. 사실은 늦어도 사실이다.
        assertThat(outcome.occupancy()).isEqualTo(OccupancyStatus.HOME);
        assertThat(outcome.greeting()).isNull();
    }

    // ── 완료 조건 4: 확정 occupancy 가 남는다 ────────────────────────────────

    @Test
    void theConfirmedOccupancyReachesTheRobotAndTheEventLog() {
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.MOTION, now, null);
        service.accept(seniorId, Signal.DOOR_OPENED, now.plusSeconds(2), null);

        assertThat(robot().getOccupancyStatus()).isEqualTo(OccupancyStatus.AWAY);
        assertThat(occupancyEventRepository.findAll())
            .singleElement()
            .satisfies(event -> {
                assertThat(event.getDirection()).isEqualTo(OccupancyDirection.OUT);
                assertThat(event.getResultingOccupancy()).isEqualTo(OccupancyStatus.AWAY);
            });
    }

    @Test
    void theOutEventIsWhatTheDailyOutingCountReads() {
        /*
         * 211 의 일간 집계가 OUT 이벤트를 센다. 외출 빈도는 발화량 다음의 두 번째
         * 활동 지표이고, 급감은 우울·건강 악화 신호다.
         */
        OffsetDateTime now = OffsetDateTime.now();
        service.accept(seniorId, Signal.MOTION, now, null);
        service.accept(seniorId, Signal.DOOR_OPENED, now.plusSeconds(2), null);

        long outings = occupancyEventRepository
            .countBySeniorIdAndDirectionAndOccurredAtGreaterThanEqualAndOccurredAtLessThan(
                seniorId, OccupancyDirection.OUT, now.minusHours(1), now.plusHours(1));

        assertThat(outings).isEqualTo(1);
    }

    @Test
    void thePisOwnTimestampIsRecordedButNotUsedForOrdering() {
        /*
         * ★ 배터리 백업 RTC 가 없는 라즈베리파이는 1970년으로 부팅할 수 있다.
         *   그 값으로 순서를 매기면 귀가가 외출로 뒤집힌다.
         */
        OffsetDateTime now = OffsetDateTime.now();
        OffsetDateTime brokenClock = OffsetDateTime.parse("1970-01-01T00:00:00Z");
        service.accept(seniorId, Signal.DOOR_OPENED, now, brokenClock);

        DoorEventOutcome outcome = service.accept(
            seniorId, Signal.MOTION, now.plusSeconds(3), brokenClock);

        assertThat(outcome.direction()).isEqualTo(OccupancyDirection.IN);
        assertThat(occupancyEventRepository.findAll())
            .singleElement()
            .satisfies(event -> assertThat(event.getReportedAt()).isEqualTo(brokenClock));
    }

    private Robot robot() {
        return robotRepository.findBySeniorId(seniorId).orElseThrow();
    }
}
