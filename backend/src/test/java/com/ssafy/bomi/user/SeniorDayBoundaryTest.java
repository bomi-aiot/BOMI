package com.ssafy.bomi.user;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.user.application.SeniorDayBoundary;
import com.ssafy.bomi.user.application.SeniorDayBoundary.LocalDayWindow;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * {@code SeniorDayBoundary} 가 "어르신의 하루"를 어떻게 자르는지 고정한다
 * (S15P11E102 G1).
 *
 * <p>여기서 잠그는 것은 <b>지표와 요약이 같은 하루를 가리킨다</b>는 사실이다.
 * {@code DailyActivityMetricService.aggregate} 는 아직 자기 안의 private
 * {@code zoneOf} 로 같은 계산을 한다(activity 모듈은 다른 작업 단위라 이번에 위임으로
 * 바꾸지 않았다). 두 계산이 갈라져도 예외는 나지 않고 둘 다 그럴듯해 보이므로, 그
 * 공식을 여기 테스트로 못 박아 둔다.</p>
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class SeniorDayBoundaryTest {

    @Autowired AppUserRepository appUserRepository;
    @Autowired TestEntityManager em;

    private SeniorDayBoundary boundary;

    @BeforeEach
    void setUp() {
        boundary = new SeniorDayBoundary(appUserRepository);
    }

    @Test
    @DisplayName("어르신 자신의 시간대로 반열린 [00:00, 다음날 00:00) 구간을 만든다")
    void buildsAHalfOpenLocalDayWindow() {
        UUID seniorId = senior("Asia/Seoul");

        LocalDayWindow window = boundary.windowFor(seniorId, LocalDate.of(2026, 8, 1));

        assertThat(window.zone()).isEqualTo(ZoneId.of("Asia/Seoul"));
        assertThat(window.from().toInstant())
            .isEqualTo(OffsetDateTime.parse("2026-08-01T00:00+09:00").toInstant());
        assertThat(window.to().toInstant())
            .isEqualTo(OffsetDateTime.parse("2026-08-02T00:00+09:00").toInstant());
    }

    @Test
    @DisplayName("★ DailyActivityMetricService.aggregate 와 글자 그대로 같은 (from, to) 를 낸다")
    void matchesTheDailyActivityMetricFormula() {
        UUID seniorId = senior("Asia/Seoul");
        LocalDate day = LocalDate.of(2026, 8, 1);

        // DailyActivityMetricService.aggregate 72-75줄의 공식 그대로.
        ZoneId zone = ZoneId.of("Asia/Seoul");
        OffsetDateTime expectedFrom = day.atStartOfDay(zone).toOffsetDateTime();
        OffsetDateTime expectedTo = day.plusDays(1).atStartOfDay(zone).toOffsetDateTime();

        LocalDayWindow window = boundary.windowFor(seniorId, day);

        assertThat(window.from()).isEqualTo(expectedFrom);
        assertThat(window.to()).isEqualTo(expectedTo);
    }

    @Test
    @DisplayName("★ DST 전환일에도 from < to 이고 하루 길이가 23시간/25시간으로 정확히 나온다")
    void survivesDaylightSavingTransitions() {
        UUID seniorId = senior("America/New_York");

        // 2026-03-08: 봄으로 넘어가며 02:00 이 사라진다 → 23시간짜리 하루.
        LocalDayWindow springForward = boundary.windowFor(seniorId, LocalDate.of(2026, 3, 8));
        assertThat(springForward.from()).isBefore(springForward.to());
        assertThat(Duration.between(springForward.from(), springForward.to()))
            .isEqualTo(Duration.ofHours(23));

        // 2026-11-01: 01:00 이 두 번 있다 → 25시간짜리 하루.
        LocalDayWindow fallBack = boundary.windowFor(seniorId, LocalDate.of(2026, 11, 1));
        assertThat(fallBack.from()).isBefore(fallBack.to());
        assertThat(Duration.between(fallBack.from(), fallBack.to()))
            .isEqualTo(Duration.ofHours(25));
    }

    @Test
    @DisplayName("시간대가 빈 문자열이면 서버 기본 시간대로 폴백한다")
    void fallsBackWhenTheTimeZoneIsBlank() {
        UUID seniorId = senior("Asia/Seoul");
        // changeTimeZone 은 공백을 거부한다(그게 맞다) — DB 에 이미 들어가 버린
        // 나쁜 값을 재현하려면 필드를 직접 덮어써야 한다.
        AppUser user = appUserRepository.findById(seniorId).orElseThrow();
        ReflectionTestUtils.setField(user, "timeZone", "   ");
        appUserRepository.saveAndFlush(user);
        em.clear();

        assertThat(boundary.zoneOf(seniorId)).isEqualTo(ZoneId.systemDefault());
    }

    @Test
    @DisplayName("시간대를 파싱할 수 없어도 예외 대신 서버 기본 시간대로 떨어진다")
    void fallsBackWhenTheTimeZoneIsUnreadable() {
        UUID seniorId = senior("Asia/Seoul");
        AppUser user = appUserRepository.findById(seniorId).orElseThrow();
        ReflectionTestUtils.setField(user, "timeZone", "Mars/Olympus_Mons");
        appUserRepository.saveAndFlush(user);
        em.clear();

        assertThat(boundary.zoneOf(seniorId)).isEqualTo(ZoneId.systemDefault());
    }

    @Test
    @DisplayName("어르신 행이 아예 없어도 하루 경계는 만들어진다 — 배치가 한 행 때문에 죽지 않는다")
    void fallsBackForAnUnknownSenior() {
        assertThat(boundary.zoneOf(UUID.randomUUID())).isEqualTo(ZoneId.systemDefault());
    }

    @Test
    @DisplayName("localNow 는 같은 순간을 어르신마다 다른 시각으로 읽는다")
    void localNowIsPerSenior() {
        UUID seoul = senior("Asia/Seoul");
        UUID newYork = senior("America/New_York");
        Clock clock = Clock.fixed(Instant.parse("2026-08-06T17:20:00Z"), ZoneOffset.UTC);

        ZonedDateTime seoulNow = boundary.localNow(seoul, clock);
        ZonedDateTime newYorkNow = boundary.localNow(newYork, clock);

        assertThat(seoulNow.getHour()).isEqualTo(2);
        assertThat(seoulNow.toLocalDate()).isEqualTo(LocalDate.of(2026, 8, 7));
        assertThat(newYorkNow.getHour()).isEqualTo(13);
        assertThat(newYorkNow.toLocalDate()).isEqualTo(LocalDate.of(2026, 8, 6));
    }

    private UUID senior(String timeZone) {
        AppUser user = AppUser.create("SENIOR", "김순자");
        user.changeTimeZone(timeZone);
        AppUser saved = appUserRepository.saveAndFlush(user);
        return saved.getId();
    }
}
