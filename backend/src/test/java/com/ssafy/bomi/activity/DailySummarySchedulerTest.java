package com.ssafy.bomi.activity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.ssafy.bomi.activity.application.DailySummaryScheduler;
import com.ssafy.bomi.activity.application.DailySummaryService;
import com.ssafy.bomi.activity.application.DailySummaryService.SummaryOutcome;
import com.ssafy.bomi.activity.config.DailySummaryProperties;
import com.ssafy.bomi.activity.domain.DailyActivityMetric;
import com.ssafy.bomi.activity.repository.DailyActivityMetricRepository;
import com.ssafy.bomi.user.application.SeniorDayBoundary;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.UserStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * 일일 요약 발송 당번의 <b>시각 판정</b>을 고정한다 (S15P11E102 G2).
 *
 * <p>{@code MedicationReminderSchedulerTest} 관례를 따른다 — 순수 Mockito + 고정 시계,
 * 스프링 컨텍스트 없음. 기존 {@code DailySummaryServiceTest} 는 EmbeddedPostgres
 * {@code @SpringBootTest} 라 "지금이 그 어르신의 아침인가"를 검증하기에는 과하고 느리다.
 * 그쪽은 발송 서비스의 완료 조건을, 이쪽은 <b>누구를 언제 부르는가</b>를 지킨다.</p>
 *
 * <p>이 테스트가 없으면 조용히 깨지는 것: 시각·시간대 판정은 예외를 내지 않는다.
 * 틀리면 "요약이 새벽에 갔다"거나 "두 번째 어르신만 못 받는다"로 나타나는데, 둘 다
 * 로그로는 정상과 구분되지 않는다.</p>
 */
class DailySummarySchedulerTest {

    private static final ZoneId KST = ZoneId.of("Asia/Seoul");
    private static final ZoneId NEW_YORK = ZoneId.of("America/New_York");

    /** 어르신 로컬 2026-08-07 08:05 → 보내야 할 날짜는 전날인 8월 6일. */
    private static final String IN_WINDOW = "2026-08-07T08:05:00";
    private static final LocalDate YESTERDAY = LocalDate.of(2026, 8, 6);

    private final AppUserRepository appUserRepository = mock(AppUserRepository.class);
    private final DailyActivityMetricRepository metricRepository =
        mock(DailyActivityMetricRepository.class);
    private final DailySummaryService summaryService = mock(DailySummaryService.class);
    private final SeniorDayBoundary dayBoundary = mock(SeniorDayBoundary.class);
    private final DailySummaryProperties properties = new DailySummaryProperties();

    private final UUID seoulSenior = UUID.randomUUID();
    private final UUID newYorkSenior = UUID.randomUUID();

    @BeforeEach
    void defaultsAreASingleSeoulSeniorWhoHasNotBeenSentYet() {
        seniors(seoulSenior);
        zoneOf(seoulSenior, KST);
        when(metricRepository.findBySeniorIdAndMetricDate(any(), any()))
            .thenReturn(Optional.empty());
        when(summaryService.sendDailySummary(any(), any()))
            .thenReturn(new SummaryOutcome(true, null));
    }

    // --- 창 판정 --------------------------------------------------------------

    @Test
    @DisplayName("★ 아침 창 안의 첫 틱은 '어제' 날짜로 정확히 한 번 보낸다")
    void theFirstTickInsideTheMorningWindowSendsYesterday() {
        schedulerAt(IN_WINDOW).tick();

        ArgumentCaptor<LocalDate> metricDate = ArgumentCaptor.forClass(LocalDate.class);
        verify(summaryService).sendDailySummary(eq(seoulSenior), metricDate.capture());
        assertThat(metricDate.getValue())
            .as("진행 중인 오늘을 집계하면 저녁 활동이 통째로 빠진 하루가 보호자에게 간다")
            .isEqualTo(YESTERDAY);
    }

    @Test
    @DisplayName("★ 새벽에는 아무도 부르지 않는다 — 일간 요약 '생성'(현지 2~3시)과 다른 시각이다")
    void nothingIsSentAtTheGenerationHour() {
        // 이 테스트가 "왜 G1 과 다른 시각인가"를 코드로 고정하는 자리다. 발송을 생성
        // 틱에 얹으면 새벽에 보호자를 깨우고, 무시되기 시작한 채널의 대가는 T2 가 아니라
        // T1(생명 안전)이 치른다.
        schedulerAt("2026-08-07T03:00:00").tick();

        verifyNoInteractions(summaryService);
    }

    @Test
    @DisplayName("창 밖(직전·경계 끝)에서는 보내지 않는다 — 반열린 구간 [08:00, 08:30)")
    void theWindowIsHalfOpen() {
        schedulerAt("2026-08-07T07:59:59").tick();
        schedulerAt("2026-08-07T08:30:00").tick();

        verifyNoInteractions(summaryService);
    }

    @Test
    @DisplayName("창의 시작 정각은 포함된다")
    void theWindowIncludesItsStart() {
        schedulerAt("2026-08-07T08:00:00").tick();

        verify(summaryService).sendDailySummary(eq(seoulSenior), eq(YESTERDAY));
    }

    // --- 시간대 ---------------------------------------------------------------

    @Test
    @DisplayName("★ 시간대가 다른 두 어르신은 각자 자기 아침에 발송된다")
    void eachSeniorIsJudgedInTheirOwnZone() {
        seniors(seoulSenior, newYorkSenior);
        zoneOf(seoulSenior, KST);
        zoneOf(newYorkSenior, NEW_YORK);

        // 서울 08:05 = 뉴욕 전날 19:05. 고정 cron 하나로 처리했을 때 깨지는 바로 그 지점.
        schedulerAt(IN_WINDOW).tick();

        verify(summaryService).sendDailySummary(eq(seoulSenior), eq(YESTERDAY));
        verify(summaryService, times(1)).sendDailySummary(any(), any());
    }

    @Test
    @DisplayName("★ 뉴욕 어르신은 뉴욕이 아침일 때 자기 '어제'로 발송된다")
    void theNewYorkSeniorIsSentDuringTheirOwnMorning() {
        seniors(seoulSenior, newYorkSenior);
        zoneOf(seoulSenior, KST);
        zoneOf(newYorkSenior, NEW_YORK);

        // 뉴욕 2026-08-07 08:05 (EDT) = 서울 21:05. 서울 어르신은 창 밖이다.
        DailySummaryScheduler scheduler = schedulerAt(IN_WINDOW, NEW_YORK);
        scheduler.tick();

        verify(summaryService).sendDailySummary(eq(newYorkSenior), eq(YESTERDAY));
        verify(summaryService, times(1)).sendDailySummary(any(), any());
    }

    @Test
    @DisplayName("시간대를 읽을 수 없어도 건너뛰지 않는다 — 폴백 시간대로 그대로 판정한다")
    void anUnreadableZoneFallsBackInsteadOfSkipping() {
        // SeniorDayBoundary 가 값이 깨졌을 때 서버 기본 시간대 + WARN 으로 떨어지는 것은
        // 그쪽 계약이고 SeniorDayBoundaryTest 가 고정한다. 여기서 지키는 것은 그 다음
        // 줄이다 — 폴백된 시간대를 받은 스케줄러가 그 어르신을 조용히 건너뛰면, 그
        // 사람만 영원히 요약을 못 받고 그 사실은 아무 데도 안 남는다.
        zoneOf(seoulSenior, ZoneId.systemDefault());

        schedulerAt(IN_WINDOW, ZoneId.systemDefault()).tick();

        verify(summaryService).sendDailySummary(eq(seoulSenior), eq(YESTERDAY));
    }

    // --- 멱등성 ---------------------------------------------------------------

    @Test
    @DisplayName("★ 이미 보낸 날은 조용히 넘어간다 — sendDailySummary 를 아예 부르지 않는다")
    void anAlreadySentDayIsSkippedWithoutCallingTheService() {
        // 부르면 ALREADY_SENT 를 돌려받기 전에 aggregate() 가 먼저 돌고 info 로그가
        // 창 안에서 매분 찍힌다.
        when(metricRepository.findBySeniorIdAndMetricDate(seoulSenior, YESTERDAY))
            .thenReturn(Optional.of(sentMetric()));

        schedulerAt(IN_WINDOW).tick();

        verifyNoInteractions(summaryService);
    }

    @Test
    @DisplayName("★ 같은 창의 두 번째·세 번째 틱은 다시 시도하지 않는다 (동의 없어 미배달이어도)")
    void laterTicksInTheSameWindowDoNotRetry() {
        // 동의 미승인이면 summary_sent_at 이 남지 않아 DB 가드가 걸리지 않는다.
        // 인메모리 가드가 없으면 30분 창 동안 미배달 care_record 가 30행 쌓인다.
        when(summaryService.sendDailySummary(any(), any()))
            .thenReturn(new SummaryOutcome(false, "CONSENT_NOT_GRANTED"));

        DailySummaryScheduler scheduler = schedulerAt(IN_WINDOW);
        scheduler.tick();
        tickAt(scheduler, "2026-08-07T08:06:00", KST);
        tickAt(scheduler, "2026-08-07T08:07:00", KST);

        verify(summaryService, times(1)).sendDailySummary(eq(seoulSenior), eq(YESTERDAY));
    }

    @Test
    @DisplayName("★ 하루가 바뀌면 같은 인스턴스라도 다시 시도한다 — 가드 키는 날짜다")
    void theNextDayIsAttemptedAgain() {
        when(summaryService.sendDailySummary(any(), any()))
            .thenReturn(new SummaryOutcome(false, "CONSENT_NOT_GRANTED"));

        DailySummaryScheduler scheduler = schedulerAt(IN_WINDOW);
        scheduler.tick();
        tickAt(scheduler, "2026-08-08T08:05:00", KST);

        verify(summaryService).sendDailySummary(eq(seoulSenior), eq(YESTERDAY));
        verify(summaryService).sendDailySummary(eq(seoulSenior), eq(LocalDate.of(2026, 8, 7)));
    }

    // --- 격리 -----------------------------------------------------------------

    @Test
    @DisplayName("★ 한 어르신의 예외가 나머지를 막지 않는다")
    void oneFailingSeniorDoesNotBlockTheRest() {
        seniors(seoulSenior, newYorkSenior);
        zoneOf(seoulSenior, KST);
        zoneOf(newYorkSenior, KST); // 둘 다 창 안에 두어 격리만 시험한다
        when(summaryService.sendDailySummary(eq(seoulSenior), any()))
            .thenThrow(new IllegalStateException("boom"));

        schedulerAt(IN_WINDOW).tick();

        verify(summaryService).sendDailySummary(eq(newYorkSenior), eq(YESTERDAY));
    }

    @Test
    @DisplayName("★ 살아 있는 SENIOR 만 조회한다 — 탈퇴·정지 계정과 보호자는 조회에서 빠진다")
    void onlyActiveSeniorsAreQueried() {
        // status 를 호출부 if 로 거르면 언젠가 빠뜨린다. 탈퇴한 어르신의 하루가 계속
        // 보호자에게 나가는 것은 낭비가 아니라 사고다.
        schedulerAt(IN_WINDOW).tick();

        verify(appUserRepository).findByUserTypeAndStatusOrderByIdAsc("SENIOR", UserStatus.ACTIVE);
    }

    // --- 설정 -----------------------------------------------------------------

    @Test
    @DisplayName("발송 시각 기본값은 어르신 로컬 아침이다 — 생성 배치(현지 2~3시)와 겹치지 않는다")
    void theDefaultSendTimeIsMorning() {
        assertThat(properties.getSendAtLocal().getHour())
            .as("새벽에 울리는 알림은 다음부터 무시되고, 그 대가는 T1 이 치른다")
            .isBetween(6, 11);
    }

    // --- 헬퍼 -----------------------------------------------------------------

    private DailySummaryScheduler schedulerAt(String isoLocalDateTime) {
        return schedulerAt(isoLocalDateTime, KST);
    }

    /** {@code zone} 의 벽시계로 그 시각에 멈춘 스케줄러. */
    private DailySummaryScheduler schedulerAt(String isoLocalDateTime, ZoneId zone) {
        lastClock = new MutableClock(instantAt(isoLocalDateTime, zone), zone);
        return new DailySummaryScheduler(appUserRepository, metricRepository, summaryService,
            dayBoundary, properties, lastClock);
    }

    /**
     * 같은 인스턴스의 시계만 앞으로 옮겨 다시 틱한다.
     *
     * <p>인메모리 중복 가드가 인스턴스 상태라, 새 인스턴스를 만들면 그 가드를 시험할 수
     * 없다 — "두 번째 틱은 재시도하지 않는다"가 항상 통과해 버린다.</p>
     */
    private void tickAt(DailySummaryScheduler scheduler, String isoLocalDateTime, ZoneId zone) {
        lastClock.moveTo(instantAt(isoLocalDateTime, zone));
        scheduler.tick();
    }

    private MutableClock lastClock;

    private static Instant instantAt(String isoLocalDateTime, ZoneId zone) {
        return ZonedDateTime.of(LocalDateTime.parse(isoLocalDateTime), zone).toInstant();
    }

    /**
     * 앞으로 감을 수 있는 시계.
     *
     * <p>{@code Clock.fixed} 를 새로 만들어 스케줄러의 {@code final} 필드에 리플렉션으로
     * 꽂는 방법도 있지만, 그건 테스트 편의를 위해 생산 코드의 불변성을 우회하는 것이다.
     * 시계를 움직일 수 있게 만드는 편이 정직하다.</p>
     */
    private static final class MutableClock extends Clock {

        private volatile Instant instant;
        private final ZoneId zone;

        private MutableClock(Instant instant, ZoneId zone) {
            this.instant = instant;
            this.zone = zone;
        }

        void moveTo(Instant next) {
            this.instant = next;
        }

        @Override
        public ZoneId getZone() {
            return zone;
        }

        @Override
        public Clock withZone(ZoneId other) {
            return new MutableClock(instant, other);
        }

        @Override
        public Instant instant() {
            return instant;
        }
    }

    private void seniors(UUID... ids) {
        List<AppUser> users = Arrays.stream(ids)
            .map(DailySummarySchedulerTest::seniorWithId)
            .toList();
        when(appUserRepository.findByUserTypeAndStatusOrderByIdAsc("SENIOR", UserStatus.ACTIVE))
            .thenReturn(users);
    }

    private void zoneOf(UUID seniorId, ZoneId zone) {
        when(dayBoundary.zoneOf(seniorId)).thenReturn(zone);
    }

    private static AppUser seniorWithId(UUID id) {
        AppUser senior = AppUser.create("SENIOR", "김순자");
        ReflectionTestUtils.setField(senior, "id", id);
        return senior;
    }

    private static DailyActivityMetric sentMetric() {
        DailyActivityMetric metric = DailyActivityMetric.openDay(UUID.randomUUID(), YESTERDAY);
        metric.markSummarySent(OffsetDateTime.now());
        return metric;
    }
}
