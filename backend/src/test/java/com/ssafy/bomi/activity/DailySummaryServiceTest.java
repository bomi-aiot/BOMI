package com.ssafy.bomi.activity;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.activity.application.DailyActivityMetricService;
import com.ssafy.bomi.activity.application.DailySummaryService;
import com.ssafy.bomi.activity.application.DailySummaryService.SummaryOutcome;
import com.ssafy.bomi.activity.domain.DailyActivityMetric;
import com.ssafy.bomi.activity.repository.DailyActivityMetricRepository;
import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.NotificationTier;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.conversation.application.RobotConversationService;
import com.ssafy.bomi.conversation.domain.MessagePriority;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.domain.MessageTriggerType;
import com.ssafy.bomi.occupancy.domain.OccupancyDirection;
import com.ssafy.bomi.occupancy.domain.OccupancyEvent;
import com.ssafy.bomi.occupancy.repository.OccupancyEventRepository;
import com.ssafy.bomi.relationship.domain.CareRelationship;
import com.ssafy.bomi.relationship.domain.RelationshipPriority;
import com.ssafy.bomi.relationship.repository.CareRelationshipRepository;
import com.ssafy.bomi.robot.domain.OccupancyStatus;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
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
 * Verifies the completion conditions of S15P11E102-211 against a real PostgreSQL.
 *
 * <p>The four rules under test are the ones that decide whether a guardian keeps reading
 * their notifications:</p>
 *
 * <ol>
 *   <li>one summary a day, no matter how often the batch re-runs</li>
 *   <li>nothing sent without sharing consent</li>
 *   <li>a metric we could not measure stays null and never appears as zero</li>
 *   <li>T1 and T2 look different on the guardian's screen</li>
 * </ol>
 *
 * <p>Real PostgreSQL rather than H2 because {@code care_record.details} is JSONB and the
 * day-boundary arithmetic depends on {@code timestamptz} semantics.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false"
    })
@Transactional
class DailySummaryServiceTest {

    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
    private static final LocalDate DAY = LocalDate.of(2026, 8, 1);

    private static EmbeddedPostgres postgres;

    @Autowired private DailySummaryService summaryService;
    @Autowired private DailyActivityMetricService metricService;
    @Autowired private RobotConversationService conversationService;
    @Autowired private DailyActivityMetricRepository metricRepository;
    @Autowired private CareRecordRepository careRecordRepository;
    @Autowired private OccupancyEventRepository occupancyEventRepository;
    @Autowired private CareRelationshipRepository relationshipRepository;
    @Autowired private AppUserRepository appUserRepository;

    private AppUser senior;
    private AppUser guardian;

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
    void setUpPeople() {
        senior = appUserRepository.save(AppUser.create("SENIOR", "김순자", null, "순자님"));
        guardian = appUserRepository.save(AppUser.create("GUARDIAN", "김보호", null, null));
        relationshipRepository.save(CareRelationship.create(
            senior.getId(), guardian.getId(), RelationshipPriority.PRIMARY));
        grantSharingConsent();
    }

    // ── 완료 조건 1: 하루 1회만 발송 ─────────────────────────────────────────

    @Test
    void theGuardianReceivesOneSummaryNoMatterHowOftenTheBatchRuns() {
        /*
         * ★ 배치는 재실행된다. 서버 재시작, 수동 실행, 스케줄러 중복 발동.
         *
         * 같은 요약을 두 번 받은 보호자는 알림을 훑어 읽기 시작하고, 훑어 읽는 것이
         * T1 을 놓치는 방식이다.
         */
        SummaryOutcome first = summaryService.sendDailySummary(senior.getId(), DAY);
        SummaryOutcome second = summaryService.sendDailySummary(senior.getId(), DAY);
        SummaryOutcome third = summaryService.sendDailySummary(senior.getId(), DAY);

        assertThat(first.sent()).isTrue();
        assertThat(second.sent()).isFalse();
        assertThat(second.reason()).isEqualTo("ALREADY_SENT");
        assertThat(third.sent()).isFalse();
        assertThat(summaryAlerts()).hasSize(1);
    }

    @Test
    void reRunningTheBatchStillRecomputesTheRow() {
        /*
         * 발송만 막고 집계는 계속한다. 늦게 도착한 행이 있으면 반영돼야 하고,
         * 그것이 다음 날 추세의 입력이 된다.
         */
        summaryService.sendDailySummary(senior.getId(), DAY);
        recordSeniorTurn("밥 먹었어요", false);

        summaryService.sendDailySummary(senior.getId(), DAY);

        assertThat(metric().getSeniorUtteranceCount()).isEqualTo(1);
        assertThat(metricRepository.findAll()).hasSize(1);
    }

    // ── 완료 조건 2: 동의 거절 시 미발송 ─────────────────────────────────────

    @Test
    void nothingIsSentWithoutSharingConsent() {
        /*
         * ★ T1 과 달리 T2 는 동의 면제가 아니다 (CLAUDE.md §9).
         */
        senior.changeGuardianSharingConsent(ConsentStatus.DENIED);
        appUserRepository.save(senior);

        SummaryOutcome outcome = summaryService.sendDailySummary(senior.getId(), DAY);

        assertThat(outcome.sent()).isFalse();
        assertThat(outcome.reason()).isEqualTo("CONSENT_NOT_GRANTED");
        assertThat(deliverableAlerts()).isEmpty();
    }

    @Test
    void aRefusedSummaryIsNotMarkedSentSoItCanGoOutOnceConsentArrives() {
        /*
         * ★ 미동의는 '오늘은 못 보낸다'이지 '영영 안 보낸다'가 아니다.
         *
         * 발송 표시를 남기면 내일 동의를 받아도 어제 요약은 영원히 나가지 못한다.
         */
        senior.changeGuardianSharingConsent(ConsentStatus.NOT_REQUESTED);
        appUserRepository.save(senior);
        summaryService.sendDailySummary(senior.getId(), DAY);

        assertThat(metric().isSummarySent()).isFalse();

        grantSharingConsent();
        assertThat(summaryService.sendDailySummary(senior.getId(), DAY).sent()).isTrue();
    }

    @Test
    void aWithheldSummaryIsStillRecordedButNotAddressedToAnyone() {
        /*
         * 관측은 남기고 전달은 하지 않는다. 통째로 버리면 나중에 "그날 무슨 일이
         * 있었나"에 답할 수 없다.
         */
        senior.changeGuardianSharingConsent(ConsentStatus.REVOKED);
        appUserRepository.save(senior);

        summaryService.sendDailySummary(senior.getId(), DAY);

        List<CareRecord> alerts = summaryAlerts();
        assertThat(alerts).hasSize(1);
        assertThat(alerts.get(0).getRecipientGuardianId()).isNull();
    }

    // ── 완료 조건 3: 모르는 것과 0 은 다르다 ─────────────────────────────────

    @Test
    void anUnmeasuredMetricStaysNullAndNeverReachesTheGuardianAsZero() {
        /*
         * ★★ 이 표 전체가 이 규칙 위에 세워져 있다.
         *
         * 수면을 측정하지 못했는데 0 으로 저장하면, T2 추세는 "어제 한숨도 못 잤다"고
         * 보고한다. 그런 오탐이 쌓이면 보호자가 알림을 읽지 않게 되고, 그때부터
         * 진짜 응급을 놓친다.
         */
        summaryService.sendDailySummary(senior.getId(), DAY);

        DailyActivityMetric metric = metric();
        assertThat(metric.getSleepMinutes()).isNull();
        assertThat(metric.getMealCount()).isNull();
        assertThat(metric.getMoodScore()).isNull();

        Map<String, Object> payload = summaryAlerts().get(0).getDetails();
        assertThat(payload).doesNotContainKeys("sleepMinutes", "mealCount", "moodScore");
    }

    @Test
    void aSilentDayLeavesVolumeUnsetRatherThanZero() {
        /*
         * ★ 대화 행이 없는 것은 두 가지를 뜻한다. 아무도 말하지 않았거나, 로봇이
         * 오프라인이라 아무것도 보고하지 못했거나. 여기서는 구분할 수 없으므로
         * 0 을 쓰지 않는다 — 0 은 "하루 종일 한마디도 없었다"로 읽힌다.
         */
        metricService.aggregate(senior.getId(), DAY);

        assertThat(metric().getSeniorUtteranceCount()).isNull();
        assertThat(metric().getRobotUtteranceCount()).isNull();
    }

    // ── 완료 조건 4: 로봇이 보낸 대화 이벤트로 발화량 칸이 채워진다 ──────────

    @Test
    void theRobotsConversationEventsFillTheUtteranceColumns() {
        /*
         * ★★ 이 경로가 없어서 발화량 칸이 통째로 NULL 이었다 (PROGRESS §2.6).
         */
        recordSeniorTurn("오늘 며칠이야?", true);
        recordSeniorTurn("밥은 먹었어", false);
        recordRobotTurn("8월 1일이에요.");

        metricService.aggregate(senior.getId(), DAY);

        DailyActivityMetric metric = metric();
        assertThat(metric.getSeniorUtteranceCount()).isEqualTo(2);
        assertThat(metric.getRobotUtteranceCount()).isEqualTo(1);
    }

    @Test
    void seniorAndRobotVolumeAreCountedSeparately() {
        /*
         * ★ 합쳐 세면 로봇이 혼자 떠든 날이 '활발한 날'로 집계된다.
         */
        recordRobotTurn("점심 드셨어요?");
        recordRobotTurn("물 한 잔 드시겠어요?");
        recordRobotTurn("어르신, 괜찮으세요?");

        metricService.aggregate(senior.getId(), DAY);

        assertThat(metric().getSeniorUtteranceCount()).isZero();
        assertThat(metric().getRobotUtteranceCount()).isEqualTo(3);
    }

    @Test
    void orientationRepeatsAreCountedFromWhatTheRobotFlagged() {
        /*
         * ★ 서버가 본문을 다시 분석하지 않는다. 로봇이 이미 분류했고, 두 곳에서
         * 판정하면 두 곳이 갈라진다.
         */
        recordSeniorTurn("오늘 며칠이야?", true);
        recordSeniorTurn("오늘 무슨 요일이지?", true);
        recordSeniorTurn("손자가 언제 온다고 했지", false);

        metricService.aggregate(senior.getId(), DAY);

        assertThat(metric().getOrientationQuestionRepeatCount()).isEqualTo((short) 2);
    }

    @Test
    void anUnflaggedTurnIsNotCountedAsNotAsking() {
        /*
         * ★ null 은 false 가 아니다. 분류하지 않은 채널(앱)의 행을 "안 물었다"로
         * 읽으면 인지 저하가 개선으로 보고된다.
         */
        conversationService.record(senior.getId(), null, MessageRole.SENIOR,
            "오늘 며칠이야?", noon(), MessageTriggerType.USER, null, null);

        metricService.aggregate(senior.getId(), DAY);

        assertThat(metric().getOrientationQuestionRepeatCount()).isZero();
    }

    @Test
    void yesterdaysTurnsDoNotCountTowardToday() {
        /*
         * 반열린 구간이라 자정 경계가 두 날에 동시에 잡히지 않는다.
         */
        conversationService.record(senior.getId(), null, MessageRole.SENIOR, "어제 말",
            DAY.minusDays(1).atTime(23, 59).atZone(SEOUL).toOffsetDateTime(),
            MessageTriggerType.USER, null, false);
        recordSeniorTurn("오늘 말", false);

        metricService.aggregate(senior.getId(), DAY);

        assertThat(metric().getSeniorUtteranceCount()).isEqualTo(1);
    }

    // ── 외출 횟수: 발화량 다음의 두 번째 활동 지표 ───────────────────────────

    @Test
    void outingsAreCountedFromOccupancyEvents() {
        occupancyEventRepository.save(OccupancyEvent.passage(senior.getId(), null,
            OccupancyDirection.OUT, OccupancyStatus.AWAY, noon(), null));
        occupancyEventRepository.save(OccupancyEvent.passage(senior.getId(), null,
            OccupancyDirection.IN, OccupancyStatus.HOME, noon().plusHours(2), null));
        occupancyEventRepository.save(OccupancyEvent.passage(senior.getId(), null,
            OccupancyDirection.OUT, OccupancyStatus.AWAY, noon().plusHours(4), null));

        metricService.aggregate(senior.getId(), DAY);

        assertThat(metric().getOutingCount()).isEqualTo((short) 2);
    }

    // ── 복약: 분자는 세고 분모는 비운다 ──────────────────────────────────────

    @Test
    void dosesTakenAreCountedButTheScheduledDenominatorStaysNull() {
        /*
         * ★ 예정 횟수는 반복 규칙을 펼쳐야 나오고, 그 로직은 224 에 이미 있다.
         *   여기서 다시 만들면 대시보드와 요약이 서로 다른 이행률을 말하게 된다.
         *
         *   V4 가 분자와 분모를 따로 저장하는 이유가 이것이다 — "3번 복용"이라고만
         *   말하고 비율은 주장하지 않을 수 있다.
         */
        careRecordRepository.save(medicationTaken(noon()));
        careRecordRepository.save(medicationTaken(noon().plusHours(6)));

        metricService.aggregate(senior.getId(), DAY);

        assertThat(metric().getMedicationTakenCount()).isEqualTo((short) 2);
        assertThat(metric().getMedicationScheduledCount()).isNull();
    }

    @Test
    void aDoseWithAnUnreadableTimeIsSkippedRatherThanCountedIntoToday() {
        /*
         * 엉뚱한 날로 붙이는 것이 세지 않는 것보다 나쁘다. 보호자가 있지도 않았던
         * 복약 이행을 보게 된다.
         */
        CareRecord broken = CareRecord.create(senior.getId(), "MEDICATION_TAKEN",
            Map.of("scheduledAt", "어제 점심때쯤"));
        careRecordRepository.save(broken);

        metricService.aggregate(senior.getId(), DAY);

        assertThat(metric().getMedicationTakenCount()).isZero();
    }

    // ── 보내는 것: 집계와 이상치만 ───────────────────────────────────────────

    @Test
    void theSummaryCarriesAggregatesNotTheConversation() {
        /*
         * ★ 원본 대화 기록이나 이동 기록은 보내지 않는다. 매일 "14:03 외출"은
         * 감시이고, "오늘 유난히 오래 나가 계셨어요"는 돌봄이다 (CLAUDE.md §9, §11).
         */
        recordSeniorTurn("남편 얘기가 나오면 아직도 힘들어", false);
        occupancyEventRepository.save(OccupancyEvent.passage(senior.getId(), null,
            OccupancyDirection.OUT, OccupancyStatus.AWAY, noon(), null));

        summaryService.sendDailySummary(senior.getId(), DAY);

        String payload = summaryAlerts().get(0).getDetails().toString();
        assertThat(payload).doesNotContain("남편");
        assertThat(payload).contains("outingCount");
    }

    @Test
    void theSummaryIsSentAsT2AndAddressedToThePrimaryGuardian() {
        summaryService.sendDailySummary(senior.getId(), DAY);

        CareRecord alert = summaryAlerts().get(0);
        assertThat(alert.getNotificationTier()).isEqualTo(NotificationTier.T2);
        assertThat(alert.getRecipientGuardianId()).isEqualTo(guardian.getId());
    }

    // ── 헬퍼 ────────────────────────────────────────────────────────────────

    private void grantSharingConsent() {
        senior.changeGuardianSharingConsent(ConsentStatus.GRANTED);
        senior = appUserRepository.save(senior);
    }

    private OffsetDateTime noon() {
        return DAY.atTime(12, 0).atZone(SEOUL).toOffsetDateTime();
    }

    private void recordSeniorTurn(String content, boolean orientationQuestion) {
        conversationService.record(senior.getId(), null, MessageRole.SENIOR, content,
            noon(), MessageTriggerType.USER, null, orientationQuestion);
    }

    private void recordRobotTurn(String content) {
        conversationService.record(senior.getId(), null, MessageRole.ROBOT, content,
            noon(), MessageTriggerType.SCHEDULE, MessagePriority.MEDIUM, null);
    }

    private CareRecord medicationTaken(OffsetDateTime scheduledAt) {
        return CareRecord.create(senior.getId(), "MEDICATION_TAKEN",
            Map.of("scheduledAt", scheduledAt.toString(), "medicationName", "혈압약"));
    }

    private DailyActivityMetric metric() {
        return metricRepository.findBySeniorIdAndMetricDate(senior.getId(), DAY).orElseThrow();
    }

    private List<CareRecord> summaryAlerts() {
        return careRecordRepository.findBySeniorId(senior.getId()).stream()
            .filter(record -> "GUARDIAN_ALERT".equals(record.getRecordType()))
            .filter(record -> record.getNotificationTier() == NotificationTier.T2)
            .toList();
    }

    private List<CareRecord> deliverableAlerts() {
        return summaryAlerts().stream()
            .filter(record -> record.getRecipientGuardianId() != null)
            .toList();
    }
}
