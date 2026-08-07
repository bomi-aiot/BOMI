package com.ssafy.bomi.activity.application;

import com.ssafy.bomi.activity.application.DailySummaryService.SummaryOutcome;
import com.ssafy.bomi.activity.config.DailySummaryProperties;
import com.ssafy.bomi.activity.repository.DailyActivityMetricRepository;
import com.ssafy.bomi.user.application.SeniorDayBoundary;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.UserStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 보호자 일일 요약의 유일한 호출자 (S15P11E102 G2).
 *
 * <p><b>이 빈이 없으면 무엇이 조용히 깨지는가.</b> {@link DailySummaryService#sendDailySummary}
 * 는 호출자가 0건이었다. 집계({@link DailyActivityMetricService})도, 중복 방지
 * ({@code summary_sent_at})도, 동의 게이트({@code GuardianAlertService})도 전부 구현된 채
 * 테스트까지 통과하고 있었는데 <b>아무도 부르지 않아서</b> 보호자는 하루 요약을 한 번도
 * 받은 적이 없다. 실패가 아니라 침묵이라 로그에도 남지 않았다 — 예외가 없으니 알림도
 * 없고, "요약이 안 왔다"고 말해 줄 사람은 애초에 요약을 받아 본 적이 없는 보호자뿐이다.</p>
 *
 * <h2>발송 시각은 어르신 로컬 아침 8시다 (기본값)</h2>
 *
 * <p>일간 요약 <em>생성</em> 배치는 어르신 현지 <b>새벽 2~3시</b>다
 * ({@code docs/database/mvp-erd.md:399} 및 같은 문서 587행 표, G1 이
 * {@code bomi.llm.daily-summary-hour=2} 로 구현했다). 발송을 그 틱에 얹지 않은 이유는
 * 세 가지이고, 셋 다 되돌리기 전에 읽어야 하는 이유다.</p>
 *
 * <ol>
 *   <li><b>집계는 DB 만 만지는 일이고, 발송은 사람에게 닿는 일이다.</b> 두 일의 옳은
 *       시각이 다르다. 새벽 3시에 보호자 휴대폰을 울리면 그 보호자는 알림을 끈다. 그리고
 *       알림이 꺼진 채널은 T1(생명 안전 — 동의조차 면제하는 등급,
 *       {@code NotificationTier} 자바독)이 갈 곳을 잃는다. <b>T2 를 잘못된 시각에 보내는
 *       비용은 T2 가 아니라 T1 이 치른다.</b></li>
 *   <li><b>순서 보장.</b> 생성(2~3시)과 발송(8시) 사이에 다섯 시간 여유를 두면 G1 이
 *       늦거나 실패한 날에도 아침 발송은 완성된 하루를 집는다. 같은 틱이면 반쯤 집계된
 *       하루가 나간다.</li>
 *   <li><b>늦게 도착한 행까지 들어온다.</b> 자정 이후 여덟 시간이면 로봇이 오프라인이었다
 *       재전송한 발화·복약 기록이 도착할 시간이 있다. 아침 집계가 새벽 집계보다 정확한
 *       하루가 된다.</li>
 * </ol>
 *
 * <p><b>지금은 아무 휴대폰도 울리지 않는다.</b> 정직하게 적어 둔다: 이 백엔드에는
 * FCM·APNs·SMTP·WebPush 코드가 한 줄도 없다. {@code GuardianAlertService.accept()} 가
 * 하는 일은 {@code care_record} 한 행({@code record_type='GUARDIAN_ALERT'},
 * {@code notification_tier=T2})을 저장하는 것이 전부이고, {@code AlertOutcome.delivered()}
 * 의 뜻은 "닿았다"가 아니라 <b>"수신자가 정해졌다"</b>(동의가 있고 주 보호자가 있다)이다.
 * 보호자는 가디언웹이 폴링하는 대시보드로만 그것을 본다. 그런데도 시각을 아침으로 두는
 * 이유는, 푸시가 붙는 날 이 파일을 다시 고치지 않아도 되게 하기 위해서다 —
 * <b>그날 고치는 것을 잊는 것이 정확히 "새벽 3시 알림"이 태어나는 방식이다.</b></p>
 *
 * <h2>고정 cron 하나로 처리하지 않는 이유</h2>
 *
 * <p>컨테이너 시계는 UTC 이고 어르신마다 {@code app_user.time_zone} 이 다르다. UTC 고정
 * cron 은 정확히 한 시간대의 어르신만 아침에 맞히고 나머지는 한밤중에 보낸다. 그 오차는
 * 예외 하나 없이 "그럴듯하게 잘못된" 결과로 나타난다. 그래서 매분 깨어나 어르신마다
 * <b>그 사람의 로컬 시각</b>으로 창을 판정한다.</p>
 *
 * <p>시간대 해석은 {@link SeniorDayBoundary} 에 위임한다 — 직접 구현하면
 * {@code DailyActivityMetricService} 의 하루 경계 규칙과 두 벌이 되고, 갈라지는 순간
 * "8시라고 판단한 날짜"와 "집계한 24시간"이 어긋난다. 그 결과 역시 그럴듯해 보인다.</p>
 *
 * <h2>{@code @Transactional} 을 붙이지 않는다</h2>
 *
 * <p>{@code MedicationReminderScheduler}/{@code ScenarioTimeoutWatchdog} 와 다른 유일한
 * 지점이고 의도적이다. 틱 전체를 한 트랜잭션으로 묶으면 마지막 어르신에서 터진 예외가
 * 앞선 어르신들의 {@code summary_sent_at} 까지 롤백하고, 그 결과는 <b>다음 날 재발송</b>
 * — 보호자가 훑어 읽기 시작하는 바로 그 사고다. {@link DailySummaryService#sendDailySummary}
 * 자체가 {@code @Transactional} 이므로 어르신 한 명이 트랜잭션 하나가 된다.</p>
 */
@Component
@ConditionalOnProperty(
    prefix = "bomi.daily-summary", name = "enabled",
    havingValue = "true", matchIfMissing = true)
public class DailySummaryScheduler {

    private static final Logger log = LoggerFactory.getLogger(DailySummaryScheduler.class);

    /** {@code app_user.user_type} 은 아직 enum 이 아니다 ({@code AppUser} 자바독 참고). */
    private static final String SENIOR = "SENIOR";

    private final AppUserRepository appUserRepository;
    private final DailyActivityMetricRepository metricRepository;
    private final DailySummaryService summaryService;
    private final SeniorDayBoundary dayBoundary;
    private final DailySummaryProperties properties;
    private final Clock clock;

    /**
     * 같은 창의 두 번째 틱이 다시 시도하지 않게 하는, 프로세스 로컬 기억.
     *
     * <p><b>DB 가드가 있는데 왜 또 필요한가.</b> 동의 미승인이거나 주 보호자가 아직
     * 없으면 {@code sendDailySummary} 는 {@code summary_sent_at} 을 남기지 <b>않는다</b> —
     * 그리고 그게 맞다. 내일 동의를 받으면 그때는 나갈 수 있어야 하니까. 문제는 그
     * 상태에서 DB 가드가 걸리지 않는다는 것이다. 30분 창을 매분 폴링하면
     * {@code GuardianAlertService.save()} 가 <b>미배달 care_record 를 30행</b> 새로 쓴다.</p>
     *
     * <p><b>비대칭이 이 설계의 핵심이다.</b> 배달된 요약의 중복은 DB
     * ({@code summary_sent_at})가 막고, 인메모리 가드는 미배달 행의 폭증만 막는다.
     * 이 맵이 유실됐을 때(재기동)의 최악은 "그 하루에 미배달 행이 하나 더 생긴다"이지
     * 보호자가 요약을 두 번 받는 것이 아니다.</p>
     *
     * <p><b>★ 이 가드가 막지 못하는 것 — 단일 인스턴스 전제 (리뷰 지적, 정정).</b>
     * 이 자리에 원래 "DB 가 <em>영구히</em> 막는다"고 적혀 있었는데 그것은 <b>백엔드
     * 인스턴스가 하나일 때만</b> 참이다. {@code summary_sent_at} 확인은 잠금 없는 읽기
     * ({@code READ COMMITTED}, {@code SELECT ... FOR UPDATE} 없음)이고, 이 맵은 프로세스
     * 로컬이다. 롤링 배포 중이거나 replica 가 둘이면 두 인스턴스의 틱이 같은 창에 들어와
     * 각자 {@code summary_sent_at = null} 을 읽고 <b>둘 다 발송</b>할 수 있다. 그러면
     * 보호자가 같은 날 요약을 두 번 받는다 — 이 자바독이 "훑어 읽기 시작하는 바로 그
     * 사고"라고 적어 둔 상태다.</p>
     *
     * <p>형제 잡인 일간 요약 <em>생성</em>은 {@code uq_conversation_summary_period} 라는 DB
     * 제약이 최종 방어선이라 이 문제가 없다. 발송 쪽에는 대응물이 없고, 만들려면
     * {@code daily_activity_metric} 에 제약이나 잠금 컬럼이 필요하다 — 즉 <b>새 마이그레이션</b>이
     * 필요하고 그것은 이 티켓 범위 밖이다. 여기서는 없는 보장을 적어 두지 않는 것까지만
     * 한다: <b>현재 이 잡은 단일 인스턴스 배포를 전제한다.</b> 다중 인스턴스로 갈 때
     * 반드시 함께 처리해야 한다.</p>
     *
     * <p>키가 날짜인 이유 — 다음 날 창에서는 {@code metricDate} 가 달라지므로 자동으로
     * 다시 시도된다. 어르신 한 명당 항목 하나이니 무한히 자라지 않는다.</p>
     */
    private final Map<UUID, LocalDate> attemptedDay = new ConcurrentHashMap<>();

    public DailySummaryScheduler(
        AppUserRepository appUserRepository,
        DailyActivityMetricRepository metricRepository,
        DailySummaryService summaryService,
        SeniorDayBoundary dayBoundary,
        DailySummaryProperties properties,
        Clock clock
    ) {
        this.appUserRepository = appUserRepository;
        this.metricRepository = metricRepository;
        this.summaryService = summaryService;
        this.dayBoundary = dayBoundary;
        this.properties = properties;
        this.clock = clock;
    }

    /**
     * 창 안에 들어온 어르신에게 전날 요약을 보낸다.
     *
     * <p>예외를 통째로 삼킨다 — 스케줄러 메서드에서 예외가 새어 나가면 스프링이 그 잡을
     * 조용히 제거한다. 그러면 증상은 "어느 날부터 요약이 안 온다"이고, 아무도 그 시작일을
     * 모른다.</p>
     */
    @Scheduled(
        fixedDelayString = "${bomi.daily-summary.tick-interval-millis:60000}",
        initialDelayString = "${bomi.daily-summary.tick-interval-millis:60000}")
    public void tick() {
        try {
            for (AppUser senior : appUserRepository.findByUserTypeAndStatusOrderByIdAsc(
                SENIOR, UserStatus.ACTIVE)) {
                try {
                    sendIfLocalMorning(senior);
                } catch (RuntimeException error) {
                    // 한 명의 실패가 나머지를 막으면 안 된다. 어르신 A 의 요약 실패로
                    // 어르신 B 의 하루가 통째로 사라지면, 그 사실은 대시보드에서
                    // "조용한 하루"와 구분되지 않는다.
                    log.error("daily summary failed for senior {}; the other seniors continue",
                        senior.getId(), error);
                }
            }
        } catch (RuntimeException error) {
            log.error("daily summary tick failed; will retry next tick", error);
        }
    }

    /**
     * 이 어르신에게 지금이 아침 창인지 보고, 맞으면 <b>전날</b> 요약을 보낸다.
     *
     * <p><b>왜 항상 전날인가.</b> 집계가 정확해지는 시점은 그 로컬 날짜가 끝난 뒤다.
     * 진행 중인 오늘을 집계하면 저녁 활동이 통째로 빠진 하루가 보호자에게 간다 — 그리고
     * 그 요약은 "조용한 하루"처럼 읽힌다.</p>
     */
    private void sendIfLocalMorning(AppUser senior) {
        UUID seniorId = senior.getId();
        ZoneId zone = dayBoundary.zoneOf(seniorId);
        ZonedDateTime localNow = ZonedDateTime.now(clock).withZoneSameInstant(zone);

        // 창 판정을 LocalTime 산술이 아니라 ZonedDateTime 비교로 하는 이유:
        // LocalTime 으로 더하면 창이 자정을 넘길 때 start > end 가 되어
        // "start <= now && now < end" 가 조용히 뒤집힌다(AppUser.quietHoursStart 자바독이
        // 같은 함정을 기록해 뒀다). 아침 시각에는 걸리지 않지만, 누군가 23:50 을 넣는
        // 날을 위해 비교 방식을 미리 안전한 쪽에 둔다.
        //
        // atZone() 을 쓰는 것도 같은 이유 — DST 전환일에는 존재하지 않는 로컬 시각이
        // 실재한다. 그런 날 하루가 통째로 한 시간 어긋나는 것을 java.time 이 처리한다.
        ZonedDateTime slot = localNow.toLocalDate()
            .atTime(properties.getSendAtLocal())
            .atZone(zone);
        ZonedDateTime windowEnd = slot.plusMinutes(properties.getWindowMinutes());
        if (localNow.isBefore(slot) || !localNow.isBefore(windowEnd)) {
            return; // 반열린 구간 [slot, windowEnd)
        }

        LocalDate metricDate = localNow.toLocalDate().minusDays(1);

        if (metricDate.equals(attemptedDay.get(seniorId))) {
            return; // 이번 창에서 이미 한 번 시도했다 (위 attemptedDay 자바독 참고)
        }
        if (alreadySentInDb(seniorId, metricDate)) {
            // 조용히 넘어간다 — 로그도 남기지 않는다. sendDailySummary 를 부르면
            // ALREADY_SENT 를 돌려받기 '전에' aggregate() 가 먼저 돌고 info 로그가
            // 창 안에서 매분 찍힌다. 재기동 뒤에도 이 겹이 재발송을 막는다.
            attemptedDay.put(seniorId, metricDate);
            return;
        }

        // 결과를 보기 전에 시도 자체를 먼저 기록한다. 아래에서 예외가 나도 이번 창에서
        // 매분 같은 실패를 반복하지 않게 하려는 것이다 — 다음 날 창이 새 metricDate 로
        // 다시 시도한다.
        attemptedDay.put(seniorId, metricDate);

        SummaryOutcome outcome = summaryService.sendDailySummary(seniorId, metricDate);
        if (outcome.sent()) {
            log.info("daily summary sent: senior={}, date={}", seniorId, metricDate);
        } else {
            // 실패가 아니라 정직한 거절인 경우가 대부분이다(CONSENT_NOT_GRANTED /
            // NO_GUARDIAN). warn 으로 올리면 정상 동작이 매일 경고를 찍는다.
            log.info("daily summary not delivered ({}): senior={}, date={}",
                outcome.reason(), seniorId, metricDate);
        }
    }

    /**
     * 이미 보낸 날인가 — 재기동에도 견디는 진실은 DB 에만 있다.
     *
     * <p>행이 아직 없으면(집계 전) 당연히 안 보낸 것이다. 여기서 집계를 유발하지 않는
     * 것이 중요하다 — 이 검사는 "부를지 말지"를 정하는 값싼 질문이어야 한다.</p>
     */
    private boolean alreadySentInDb(UUID seniorId, LocalDate metricDate) {
        return metricRepository.findBySeniorIdAndMetricDate(seniorId, metricDate)
            .filter(metric -> metric.isSummarySent())
            .isPresent();
    }
}
