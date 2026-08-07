package com.ssafy.bomi.migration;

import static org.assertj.core.api.Assertions.assertThat;

import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Proves the V7 backfill on <strong>real PostgreSQL</strong> (S15P11E102-230).
 *
 * <p><b>Why this test exists separately from {@code FlywayMigrationValidationTest}.</b> That
 * test migrates an empty database, so a backfill has nothing to backfill — it would pass
 * whether the {@code UPDATE} worked or was deleted entirely. To actually exercise it we have
 * to stop at V6, write rows the old way, and only then apply V7. That is what this does.</p>
 *
 * <p><b>Why not H2.</b> {@code jsonb}, the {@code ?|} operator, and PL/pgSQL exception
 * blocks are all PostgreSQL. H2 would either reject the migration or, worse, accept a
 * rewritten version of it that is not the one we ship.</p>
 *
 * <p>What each case is protecting:</p>
 * <ul>
 *   <li>the four old conventions each land in the column</li>
 *   <li>a value nobody can parse leaves the row null instead of aborting the whole
 *       migration — one bad row must not stop a deploy</li>
 *   <li>a recurring schedule stays null, because it has no single point in time</li>
 * </ul>
 */
@DisplayName("V7 backfill: details 의 네 규약이 occurred_at 한 컬럼으로 모인다")
class CareRecordOccurredAtBackfillTest {

    private static EmbeddedPostgres postgres;
    private static DataSource dataSource;

    /** Every row belongs to the same fictional senior; nothing here reads app_user. */
    private static final UUID SENIOR = UUID.fromString("11111111-1111-1111-1111-111111111111");

    @BeforeAll
    static void migrateToV6AndSeed() throws Exception {
        postgres = EmbeddedPostgres.start();
        dataSource = postgres.getPostgresDatabase();

        // ★ target=6. V7 은 아직 적용하지 않는다 — 옛 방식으로 쓰인 행이 있어야
        //   백필이 실제로 무언가를 하는지 볼 수 있다.
        migrateTo("6");

        insert("MEDICATION_TAKEN",
            "{\"medicationName\":\"혈압약\",\"scheduledAt\":\"2026-08-01T09:00:00+09:00\"}");
        insert("PERSONAL_SCHEDULE",
            "{\"title\":\"내과 진료\",\"startsAt\":\"2026-08-02T14:30:00+09:00\"}");
        insert("GUARDIAN_ALERT",
            "{\"tier\":\"T1\",\"reason\":\"NO_RESPONSE\",\"ts\":1785000000}");
        insert("GUARDIAN_ALERT",
            "{\"tier\":\"T2\",\"metricDate\":\"2026-08-01\"}");
        insert("MEDICATION_TAKEN",
            "{\"medicationName\":\"당뇨약\",\"scheduledAt\":\"어제 아침\"}");
        insert("MEDICATION_SCHEDULE",
            "{\"medicationName\":\"혈압약\",\"localTimes\":[\"09:00\"]}");

        migrateTo("7");
    }

    @AfterAll
    static void stop() throws IOException {
        if (postgres != null) {
            postgres.close();
        }
    }

    @Test
    @DisplayName("MEDICATION_TAKEN 은 details.scheduledAt 의 슬롯 시각으로 채워진다")
    void isoScheduledAtIsBackfilled() throws Exception {
        assertThat(occurredAtOf("혈압약", "MEDICATION_TAKEN"))
            .isEqualTo(OffsetDateTime.of(2026, 8, 1, 9, 0, 0, 0, ZoneOffset.ofHours(9))
                .toInstant());
    }

    @Test
    @DisplayName("일정은 details.startsAt 으로 채워진다 — 현관 인사가 못 찾던 그 키다")
    void isoStartsAtIsBackfilled() throws Exception {
        assertThat(occurredAtByType("PERSONAL_SCHEDULE"))
            .isEqualTo(OffsetDateTime.of(2026, 8, 2, 14, 30, 0, 0, ZoneOffset.ofHours(9))
                .toInstant());
    }

    @Test
    @DisplayName("로봇 알림의 details.ts(epoch 초)가 채워진다")
    void epochSecondsAreBackfilled() throws Exception {
        assertThat(occurredAtOfTier("T1"))
            .isEqualTo(java.time.Instant.ofEpochSecond(1785000000L));
    }

    @Test
    @DisplayName("일일 요약 알림의 metricDate 는 '어르신 로컬 날짜의 시작'으로 채워진다")
    void localDateIsBackfilledAtSeoulMidnight() throws Exception {
        // UTC 자정으로 두면 한국 어르신의 하루 요약이 전날 09:00 으로 표시된다.
        assertThat(occurredAtOfTier("T2"))
            .isEqualTo(OffsetDateTime.of(2026, 8, 1, 0, 0, 0, 0, ZoneOffset.ofHours(9))
                .toInstant());
    }

    @Test
    @DisplayName("★ 읽을 수 없는 값은 NULL 로 남고, 마이그레이션을 죽이지 않는다")
    void anUnparseableValueLeavesTheRowNullInsteadOfFailingTheDeploy() throws Exception {
        // 이 테스트가 통과한다는 것은 @BeforeAll 의 migrateTo("7") 이 예외 없이
        // 끝났다는 뜻이기도 하다. details 는 jsonb 이고 값 형식을 아무도 강제하지
        // 않았으므로, 깨진 행 하나가 배포를 막아서는 안 된다.
        assertThat(occurredAtOf("당뇨약", "MEDICATION_TAKEN")).isNull();
    }

    @Test
    @DisplayName("반복 스케줄은 NULL 로 남는다 — 시간축의 한 점이 아니다")
    void aRecurringScheduleHasNoPointInTime() throws Exception {
        assertThat(occurredAtByType("MEDICATION_SCHEDULE")).isNull();
    }

    @Test
    @DisplayName("추세 질의용 인덱스가 생성된다")
    void theTrendIndexExists() throws Exception {
        try (Connection connection = dataSource.getConnection();
            PreparedStatement ps = connection.prepareStatement(
                "SELECT indexdef FROM pg_indexes WHERE indexname = ?")) {
            ps.setString(1, "ix_care_record_senior_type_occurred");
            try (ResultSet rs = ps.executeQuery()) {
                assertThat(rs.next()).as("인덱스가 없으면 추세 질의가 풀스캔으로 돌아간다").isTrue();
                // 컬럼 순서가 곧 질의 순서다. 순서가 바뀌면 범위 조건이 인덱스를 못 탄다.
                assertThat(rs.getString("indexdef"))
                    .contains("senior_id", "record_type", "occurred_at");
            }
        }
    }

    @Test
    @DisplayName("마이그레이션이 만든 임시 함수는 남지 않는다")
    void theHelperFunctionsAreDropped() throws Exception {
        try (Connection connection = dataSource.getConnection();
            PreparedStatement ps = connection.prepareStatement(
                "SELECT count(*) FROM pg_proc WHERE proname LIKE 'bomi_v7_%'")) {
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                // 남겨두면 다음 사람이 정식 유틸리티인 줄 알고 쓴다.
                assertThat(rs.getInt(1)).isZero();
            }
        }
    }

    // ── 도우미 ───────────────────────────────────────────────────────────────

    private static void migrateTo(String target) {
        Flyway.configure()
            .dataSource(dataSource)
            .locations("classpath:db/migration")
            .target(target)
            .load()
            .migrate();
    }

    private static void insert(String recordType, String detailsJson) throws Exception {
        try (Connection connection = dataSource.getConnection();
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO care_record (id, senior_id, record_type, status, details) "
                    + "VALUES (?, ?, ?, 'ACTIVE', ?::jsonb)")) {
            ps.setObject(1, UUID.randomUUID());
            ps.setObject(2, SENIOR);
            ps.setString(3, recordType);
            ps.setString(4, detailsJson);
            ps.executeUpdate();
        }
    }

    private static java.time.Instant occurredAtOf(String medicationName, String recordType)
        throws Exception {
        return queryInstant(
            "SELECT occurred_at FROM care_record "
                + "WHERE record_type = ? AND details ->> 'medicationName' = ?",
            recordType, medicationName);
    }

    private static java.time.Instant occurredAtByType(String recordType) throws Exception {
        return queryInstant(
            "SELECT occurred_at FROM care_record WHERE record_type = ?", recordType);
    }

    private static java.time.Instant occurredAtOfTier(String tier) throws Exception {
        return queryInstant(
            "SELECT occurred_at FROM care_record "
                + "WHERE record_type = 'GUARDIAN_ALERT' AND details ->> 'tier' = ?", tier);
    }

    private static java.time.Instant queryInstant(String sql, String... params) throws Exception {
        try (Connection connection = dataSource.getConnection();
            PreparedStatement ps = connection.prepareStatement(sql)) {
            for (int i = 0; i < params.length; i++) {
                ps.setString(i + 1, params[i]);
            }
            try (ResultSet rs = ps.executeQuery()) {
                assertThat(rs.next()).as("행이 있어야 한다: %s", sql).isTrue();
                OffsetDateTime value = rs.getObject("occurred_at", OffsetDateTime.class);
                return value == null ? null : value.toInstant();
            }
        }
    }
}
