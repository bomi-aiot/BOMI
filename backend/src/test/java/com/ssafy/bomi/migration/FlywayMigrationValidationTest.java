package com.ssafy.bomi.migration;

import static org.assertj.core.api.Assertions.assertThat;

import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * Runs every Flyway migration against an <strong>empty, real PostgreSQL</strong>
 * and then lets Hibernate {@code validate} compare the result with the entities.
 *
 * <p>This is the completion condition of S15P11E102-201, executed rather than
 * asserted by hand. It is deliberately not an H2 test: the Flyway guide notes that
 * H2 cannot catch array, JSONB, or type differences, and V1 is written in
 * PostgreSQL dialect. The {@code datajpa} slice tests use H2 with Hibernate
 * schema generation, which validates the entities against <em>themselves</em> —
 * exactly the mistake this test exists to avoid.</p>
 *
 * <p>PostgreSQL runs from a real server binary, no Docker required, so this works
 * on a developer machine and in CI without the manual WSL/Docker ritual described
 * in {@code docs/database/flyway-guide.md} §4.</p>
 *
 * <p>What a failure here means:</p>
 * <ul>
 *   <li>Context fails with {@code Schema-validation:} — an entity and the
 *       migrations disagree. Someone changed a field without adding a V file.</li>
 *   <li>Context fails with a Flyway error — the SQL itself is invalid, or an
 *       already-applied migration was edited and its checksum changed.</li>
 * </ul>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.flyway.baseline-on-migrate=false",
        // 이 테스트의 핵심. validate 는 스키마를 바꾸지 않고 엔티티와 DB 가 일치하는지만
        // 검사한다. 불일치면 컨텍스트가 아예 뜨지 않는다.
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        // MQTT 브로커가 없는 환경에서도 이 테스트가 스키마만 검증하도록 자동 연결을 끈다.
        "bomi.mqtt.enabled=false"
    })
class FlywayMigrationValidationTest {

    private static EmbeddedPostgres postgres;

    @Autowired
    private DataSource dataSource;

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

    /**
     * The context loading at all is the assertion: Flyway migrated an empty database
     * and Hibernate validated the entities against the result.
     */
    @Test
    void migrationsApplyToEmptyDatabaseAndEntitiesValidate() throws Exception {
        List<String> applied = new ArrayList<>();
        try (Connection connection = dataSource.getConnection();
            Statement statement = connection.createStatement();
            ResultSet rs = statement.executeQuery(
                "SELECT version, success FROM flyway_schema_history ORDER BY installed_rank")) {
            while (rs.next()) {
                assertThat(rs.getBoolean("success"))
                    .as("migration %s must have applied successfully", rs.getString("version"))
                    .isTrue();
                applied.add(rs.getString("version"));
            }
        }

        // V1 부터 이 티켓의 V5 까지가 순서대로 적용되어야 한다. 새 V 파일을 추가하면
        // 이 목록도 함께 늘려서, 파일만 만들고 검증을 잊는 일이 없게 한다.
        assertThat(applied).containsExactly("1", "2", "3", "4", "5", "6", "7", "8", "9", "10");
    }

    /**
     * The three tables the robot runtime reads must actually carry the new columns.
     *
     * <p>Hibernate {@code validate} already checks entity-mapped columns, so this
     * covers what it cannot see: that the columns are non-null where the safety
     * argument depends on it. A nullable {@code occupancy_status} would let a row
     * exist with no occupancy at all, and the silence ladder would have to guess.</p>
     */
    @Test
    void safetyCriticalColumnsAreNotNullable() throws Exception {
        assertThat(isNullable("app_user", "quiet_hours_start")).isFalse();
        assertThat(isNullable("app_user", "quiet_hours_end")).isFalse();
        assertThat(isNullable("robot", "occupancy_status")).isFalse();
        assertThat(isNullable("memory", "embedding_status")).isFalse();
        assertThat(isNullable("conversation_summary", "embedding_status")).isFalse();

        // 반대로, '모르는 것'을 표현해야 하는 컬럼은 NULL 을 허용해야 한다.
        // 하트비트가 NULL 이면 "아직 한 번도 못 받음"이고, 그건 0 이나 과거 시각과 다르다.
        assertThat(isNullable("robot", "door_node_heartbeat_at")).isTrue();
        // 측정하지 못한 지표를 0 으로 저장하면 T2 추세가 보호자에게 거짓을 보고한다.
        assertThat(isNullable("daily_activity_metric", "sleep_minutes")).isTrue();
        // occurred_at 의 NULL 은 두 가지를 뜻한다: '모른다', 그리고 '시점이 없다'
        // (반복 스케줄, 처방 자체). NOT NULL 로 만들면 둘 다 표현할 수 없어서
        // 마이그레이션 시각을 지어내게 된다 (S15P11E102-230).
        assertThat(isNullable("care_record", "occurred_at")).isTrue();
        // known_person.is_deceased 의 NULL 은 '모른다'다. NOT NULL 로 만들면 모르는
        // 사람을 강제로 TRUE/FALSE 중 하나로 지어내야 하고, "모르니까 언급해도
        // 된다"고 지어내는 순간이 이 제품에서 가장 위험한 실수다 (S15P11E102-260).
        assertThat(isNullable("known_person", "is_deceased")).isTrue();
        assertThat(isNullable("known_person", "senior_id")).isFalse();
        assertThat(isNullable("known_person", "display_name")).isFalse();
    }

    /** pgvector 를 쓰지 않기로 했으므로, 벡터 확장과 임베딩 컬럼이 없어야 한다. */
    @Test
    void pgvectorIsNotUsed() throws Exception {
        try (Connection connection = dataSource.getConnection();
            Statement statement = connection.createStatement();
            ResultSet rs = statement.executeQuery(
                "SELECT count(*) FROM pg_extension WHERE extname = 'vector'")) {
            rs.next();
            assertThat(rs.getInt(1))
                .as("vector 확장은 활성화되지 않아야 한다 (S15P11E102-218 로 이동)")
                .isZero();
        }
        assertThat(columnExists("memory", "embedding")).isFalse();
        assertThat(columnExists("conversation_summary", "embedding")).isFalse();
    }

    private boolean isNullable(String table, String column) throws Exception {
        try (Connection connection = dataSource.getConnection();
            var ps = connection.prepareStatement(
                "SELECT is_nullable FROM information_schema.columns "
                    + "WHERE table_name = ? AND column_name = ?")) {
            ps.setString(1, table);
            ps.setString(2, column);
            try (ResultSet rs = ps.executeQuery()) {
                assertThat(rs.next()).as("%s.%s must exist", table, column).isTrue();
                return "YES".equals(rs.getString("is_nullable"));
            }
        }
    }

    private boolean columnExists(String table, String column) throws Exception {
        try (Connection connection = dataSource.getConnection();
            var ps = connection.prepareStatement(
                "SELECT 1 FROM information_schema.columns "
                    + "WHERE table_name = ? AND column_name = ?")) {
            ps.setString(1, table);
            ps.setString(2, column);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next();
            }
        }
    }
}
