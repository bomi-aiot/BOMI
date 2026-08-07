package com.ssafy.bomi.user.application;

import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * "이 어르신의 로컬 하루"가 UTC 축에서 어디부터 어디까지인가 — 그 계산의 소유자
 * (S15P11E102 G1).
 *
 * <p><b>이 컴포넌트가 없으면 무엇이 조용히 깨지는가.</b> 하루 경계 계산은 예외를 내지
 * 않는 종류의 코드다. 시간대를 잘못 잡아도 결과는 "그럴듯한 하루"로 나오고, 지표가
 * 말하는 8월 1일과 요약이 말하는 8월 1일이 서로 다른 24시간을 가리켜도 아무 로그도
 * 남지 않는다. 그래서 계산을 한 곳에 모은다 — 두 벌이 되는 순간 언젠가 갈라지고,
 * 갈라진 사실은 보호자가 "어제 대화가 요약에 안 들어갔다"고 말하기 전까지 아무도
 * 모른다.</p>
 *
 * <p><b>원본은 {@code DailyActivityMetricService.aggregate}/{@code zoneOf} 다.</b> 폴백
 * 동작(빈 값·파싱 실패 → 서버 기본 시간대 + WARN)까지 글자 그대로 옮겼다. 그쪽
 * private {@code zoneOf} 를 이 컴포넌트 위임으로 바꾸는 3줄 변경이 남아 있으며,
 * 그때까지는 {@code SeniorDayBoundaryTest} 가 "두 계산이 같은 (from, to) 를 낸다"를
 * 고정한다. activity 모듈은 다른 작업 단위의 파일이라 이번 변경에서 손대지 않았다.</p>
 *
 * <p>구간은 언제나 <b>반열린</b> {@code [from, to)} 다. 닫힌 구간으로 만들면 자정
 * 발화가 어제와 오늘 양쪽에 한 번씩, 총 두 번 세어진다.</p>
 */
@Component
public class SeniorDayBoundary {

    private static final Logger log = LoggerFactory.getLogger(SeniorDayBoundary.class);

    private final AppUserRepository appUserRepository;

    public SeniorDayBoundary(AppUserRepository appUserRepository) {
        this.appUserRepository = appUserRepository;
    }

    /**
     * 어르신의 로컬 하루 하나와, 그것이 대응하는 UTC 반열린 구간.
     *
     * <p>{@code zone} 을 같이 들고 다니는 이유 — 호출부가 "이 구간이 어느 시간대
     * 기준으로 잘린 것인가"를 로그에 남길 수 있어야 한다. 시간대 폴백이 일어났는지는
     * 나중에 결과만 봐서는 절대 알 수 없다.</p>
     */
    public record LocalDayWindow(
        LocalDate day, ZoneId zone, OffsetDateTime from, OffsetDateTime to) {
    }

    /**
     * 어르신 자신의 시간대. 없거나 읽을 수 없으면 서버 기본 시간대로 떨어진다.
     *
     * <p>폴백은 반드시 로그를 남긴다. 조용히 틀린 시간대는 모든 하루 경계를 통째로
     * 밀어 놓고도 결과가 그럴듯해 보이므로, 가장 나쁜 종류의 오류다.</p>
     *
     * <p>{@code app_user.time_zone} 은 {@code NOT NULL DEFAULT 'Asia/Seoul'} 이라 실제로는
     * 방어용이다 — 다만 어르신 행이 아예 없는 경우(테스트 픽스처, 삭제된 사용자)에도
     * 이 경로가 하루 경계를 만들어내야 하므로 없앨 수는 없다.</p>
     */
    public ZoneId zoneOf(UUID seniorId) {
        String configured = appUserRepository.findById(seniorId)
            .map(AppUser::getTimeZone)
            .orElse(null);
        if (configured == null || configured.isBlank()) {
            log.warn("senior {} has no time zone; day boundaries fall back to the server's",
                seniorId);
            return ZoneId.systemDefault();
        }
        try {
            return ZoneId.of(configured);
        } catch (Exception error) {
            log.warn("senior {} has an unreadable time zone '{}'; falling back to the server's",
                seniorId, configured);
            return ZoneId.systemDefault();
        }
    }

    /** 어르신의 시간대를 찾아 그 로컬 날짜의 구간을 만든다. */
    public LocalDayWindow windowFor(UUID seniorId, LocalDate localDay) {
        return windowFor(zoneOf(seniorId), localDay);
    }

    /**
     * 이미 해석된 시간대로 구간을 만든다 — 저장소를 건드리지 않는 순수 계산.
     *
     * <p>한 스윕이 어르신 한 명에게 {@code zoneOf} 를 두 번 부르지 않게 하려고 나눠
     * 뒀다. 시간대 조회는 매시간 전체 어르신에게 일어난다.</p>
     *
     * <p>{@code atStartOfDay(zone)} 를 쓰는 이유 — DST 전환일에 자정이 존재하지 않거나
     * 두 번 있는 시간대가 실재한다. {@code LocalDateTime.of(day, MIDNIGHT)} 로
     * 만들어서 오프셋을 나중에 붙이면 그런 날 하루가 통째로 한 시간 어긋난다.</p>
     */
    public LocalDayWindow windowFor(ZoneId zone, LocalDate localDay) {
        OffsetDateTime from = localDay.atStartOfDay(zone).toOffsetDateTime();
        OffsetDateTime to = localDay.plusDays(1).atStartOfDay(zone).toOffsetDateTime();
        return new LocalDayWindow(localDay, zone, from, to);
    }

    /**
     * 어르신에게 "지금 몇 시인가".
     *
     * <p>{@code Clock} 을 받는 이유는 {@code SchedulingConfig} 의 주석과 같다 — 새벽 2시
     * 창을 검증하려고 테스트가 새벽 2시까지 기다릴 수는 없다.</p>
     */
    public ZonedDateTime localNow(UUID seniorId, Clock clock) {
        return clock.instant().atZone(zoneOf(seniorId));
    }
}
