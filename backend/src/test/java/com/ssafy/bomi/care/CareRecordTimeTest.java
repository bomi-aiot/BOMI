package com.ssafy.bomi.care;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

/**
 * The one rule that decides where a care record sits in time (S15P11E102-230).
 *
 * <p>This class and the {@code COALESCE} in {@code V7__add_care_record_occurred_at.sql} are
 * the same rule written twice — once for rows that already existed, once for rows still to
 * come. {@code CareRecordOccurredAtBackfillTest} covers the SQL half against real
 * PostgreSQL; this covers the Java half. If the two ever disagree, a senior's history has a
 * seam in it at the date of the deploy.</p>
 */
class CareRecordTimeTest {

    private static final UUID SENIOR = UUID.randomUUID();

    @Nested
    @DisplayName("네 가지 옛 규약을 모두 읽는다")
    class ReadsEveryOldConvention {

        @Test
        @DisplayName("scheduledAt — 복약이 매칭된 슬롯 시각 (224)")
        void scheduledAt() {
            assertThat(CareRecordTime.fromDetails(
                Map.of("scheduledAt", "2026-08-01T09:00:00+09:00")))
                .isEqualTo(at(2026, 8, 1, 9, 0));
        }

        @Test
        @DisplayName("startsAt — 일정의 시작 시각 (221)")
        void startsAt() {
            assertThat(CareRecordTime.fromDetails(
                Map.of("startsAt", "2026-08-02T14:30:00+09:00")))
                .isEqualTo(at(2026, 8, 2, 14, 30));
        }

        @Test
        @DisplayName("observedAt — 센서가 실은 관측 시각")
        void observedAt() {
            assertThat(CareRecordTime.fromDetails(
                Map.of("observedAt", "2026-08-02T03:15:00+09:00")))
                .isEqualTo(at(2026, 8, 2, 3, 15));
        }

        @Test
        @DisplayName("ts — 로봇 발신 큐가 싣는 epoch 초 (211)")
        void epochSeconds() {
            assertThat(CareRecordTime.fromDetails(Map.of("ts", 1785000000L)))
                .isEqualTo(OffsetDateTime.ofInstant(
                    java.time.Instant.ofEpochSecond(1785000000L), ZoneOffset.ofHours(9)));
        }

        @Test
        @DisplayName("★ ts 가 문자열로 와도 받는다")
        void epochSecondsAsText() {
            /*
             * JSON 을 두 번 거치는 경로에서 숫자가 문자열이 되어 도착한다. 여기서
             * 받아주지 않으면 알림이 시각 없이 저장되고, 보호자 화면에서 정렬 맨 뒤로
             * 밀린다 — 진짜 T1 이 오래된 알림들 아래에 깔린다.
             */
            assertThat(CareRecordTime.fromDetails(Map.of("ts", "1785000000")))
                .isEqualTo(CareRecordTime.fromDetails(Map.of("ts", 1785000000L)));
        }

        @Test
        @DisplayName("★ metricDate 는 '어르신 로컬 날짜의 시작'이다. UTC 자정이 아니다")
        void metricDateAtSeoulMidnight() {
            /*
             * UTC 자정으로 읽으면 한국 어르신의 하루 요약이 전날 09:00 에 붙는다.
             * 보호자 화면에서 어제 요약이 그제 것처럼 보인다.
             */
            assertThat(CareRecordTime.fromDetails(Map.of("metricDate", "2026-08-01")))
                .isEqualTo(at(2026, 8, 1, 0, 0));
        }
    }

    @Nested
    @DisplayName("모르는 것은 지어내지 않는다")
    class UnknownStaysUnknown {

        @Test
        @DisplayName("시각 키가 하나도 없으면 null")
        void noKeyAtAll() {
            assertThat(CareRecordTime.fromDetails(Map.of("medicationName", "혈압약"))).isNull();
            assertThat(CareRecordTime.fromDetails(Map.of())).isNull();
            assertThat(CareRecordTime.fromDetails(null)).isNull();
        }

        @Test
        @DisplayName("★ 읽을 수 없는 값은 null 이지 '지금'이 아니다")
        void unreadableIsNullNotNow() {
            /*
             * 파싱 실패를 지금으로 메우면, 반년 전 복용 기록이 오늘 복약 이행률에
             * 들어간다. 보호자는 있지도 않은 이행을 본다.
             */
            assertThat(CareRecordTime.fromDetails(Map.of("scheduledAt", "어제 아침"))).isNull();
            assertThat(CareRecordTime.fromDetails(Map.of("ts", "곧"))).isNull();
            assertThat(CareRecordTime.fromDetails(Map.of("metricDate", "2026-13-45"))).isNull();
        }

        @Test
        @DisplayName("fromDetailsOrNow 는 '지금 일어난 일'에만 쓴다")
        void nowIsOnlyAFallbackWhereItIsTrue() {
            OffsetDateTime now = at(2026, 8, 2, 17, 0);

            // 값이 있으면 그 값이 이긴다 — 큐에 밀렸다 도착한 알림의 진짜 시각이다.
            assertThat(CareRecordTime.fromDetailsOrNow(
                Map.of("ts", 1785000000L), now))
                .isNotEqualTo(now);
            assertThat(CareRecordTime.fromDetailsOrNow(Map.of("reason", "NO_RESPONSE"), now))
                .isEqualTo(now);
        }
    }

    @Nested
    @DisplayName("우선순위가 정해져 있다")
    class OrderIsDefined {

        @Test
        @DisplayName("구체적인 규약이 먼저 — V7 의 COALESCE 순서와 같아야 한다")
        void mostSpecificWins() {
            Map<String, Object> details = new HashMap<>();
            details.put("metricDate", "2026-01-01");
            details.put("ts", 1785000000L);
            details.put("startsAt", "2026-08-02T14:30:00+09:00");
            details.put("scheduledAt", "2026-08-01T09:00:00+09:00");

            assertThat(CareRecordTime.fromDetails(details)).isEqualTo(at(2026, 8, 1, 9, 0));
        }

        @Test
        @DisplayName("앞선 키가 깨져 있으면 다음 키로 넘어간다")
        void abrokenKeyFallsThrough() {
            Map<String, Object> details = new HashMap<>();
            details.put("scheduledAt", "언젠가");
            details.put("startsAt", "2026-08-02T14:30:00+09:00");

            assertThat(CareRecordTime.fromDetails(details)).isEqualTo(at(2026, 8, 2, 14, 30));
        }
    }

    @Nested
    @DisplayName("★ 팩토리가 details 에서 시각을 꺼낸다 — 이게 조용한 유실을 막는다")
    class TheFactoryClosesTheHole {

        @Test
        @DisplayName("occurredAt 을 부르지 않아도 컬럼이 채워진다")
        void createDerivesWithoutAnExplicitCall() {
            /*
             * ★★ 230 이 존재하는 이유가 이것이다. 새 쓰기 경로가 컬럼 설정을 잊어도,
             * details 에 시각을 넣었다면 잃지 않는다. 잊었을 때의 증상이 "컴파일도 저장도
             * 되는데 집계에서만 사라짐"이라 아무도 눈치채지 못한다.
             */
            CareRecord record = CareRecord.create(SENIOR, "MEDICATION_TAKEN",
                Map.of("medicationName", "혈압약", "scheduledAt", "2026-08-01T09:00:00+09:00"));

            assertThat(record.getOccurredAt()).isEqualTo(at(2026, 8, 1, 9, 0));
        }

        @Test
        @DisplayName("명시적으로 부르면 그쪽이 이긴다")
        void anExplicitCallOverrides() {
            CareRecord record = CareRecord.create(SENIOR, "REST_OBSERVATION",
                Map.of("restState", "RESTING"));
            assertThat(record.getOccurredAt()).isNull();

            record.occurredAt(at(2026, 8, 2, 22, 30));
            assertThat(record.getOccurredAt()).isEqualTo(at(2026, 8, 2, 22, 30));
        }

        @Test
        @DisplayName("반복 스케줄은 null 로 남는다 — 시간축의 한 점이 아니다")
        void arecurringScheduleHasNoPoint() {
            CareRecord record = CareRecord.create(SENIOR, "MEDICATION_SCHEDULE",
                Map.of("medicationName", "혈압약", "localTimes", java.util.List.of("09:00")));

            assertThat(record.getOccurredAt()).isNull();
        }
    }

    private static OffsetDateTime at(int year, int month, int day, int hour, int minute) {
        return OffsetDateTime.of(year, month, day, hour, minute, 0, 0, ZoneOffset.ofHours(9));
    }
}
