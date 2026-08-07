package com.ssafy.bomi.seed;

import static org.assertj.core.api.Assertions.assertThat;

import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;

/**
 * {@code scripts/dev/seed-kim-sunja.sql} 가 실제 스키마 위에서 그대로 실행되는지 확인한다
 * (S15P11E102-262).
 *
 * <p>왜 존재하는가 — 이 파일은 어떤 Flyway 마이그레이션도, 어떤 자바 테스트도 거치지
 * 않는 순수 개발용 스크립트다. 회상 씨앗 네 건을 추가하면서 컬럼 순서나 값 개수를
 * 하나만 틀려도, 그 사실은 사람이 직접 psql 로 실행해 보기 전까지 아무도 모른다.
 * 이 테스트가 그 "직접 실행"을 CI 로 옮긴다.</p>
 *
 * <p>Spring 컨텍스트를 올리지 않는다 — 이 테스트가 확인할 것은 스키마 위에서 SQL 이
 * 오류 없이 끝까지 실행되는가와 표 안의 행 개수뿐이라서, 전체 애플리케이션 컨텍스트를
 * 기동하는 비용이 필요 없다. Flyway 를 직접 이 DataSource 에 대고 돌려 스키마만
 * 만든다.</p>
 */
class SeedKimSunjaScriptTest {

    @Test
    void seedScriptAppliesCleanlyAndPopulatesReminiscenceSeeds() throws IOException, Exception {
        try (EmbeddedPostgres postgres = EmbeddedPostgres.start()) {
            DataSource dataSource = postgres.getPostgresDatabase();

            Flyway.configure()
                .dataSource(dataSource)
                .load()
                .migrate();

            String sql = Files.readString(
                locate(Path.of("scripts", "dev", "seed-kim-sunja.sql")), StandardCharsets.UTF_8);

            try (Connection connection = dataSource.getConnection();
                Statement statement = connection.createStatement()) {
                // pgjdbc 의 단순 프로토콜(Statement.execute(String))은 세미콜론으로 구분된
                // 여러 문장과 DO $$ ... $$ 블록을 한 번에 실행할 수 있다 — psql 로 그대로
                // 붙여넣는 것과 같은 경로다.
                statement.execute(sql);

                assertThat(count(statement, "app_user")).isEqualTo(3);
                assertThat(count(statement, "onboarding_answer")).isEqualTo(12);
                // 완료 조건: "김순자 시드에 회상 씨앗 데이터를 보강합니다" — 기존 2건 +
                // 회상 씨앗 4건.
                assertThat(count(statement, "memory")).isEqualTo(6);

                try (ResultSet rs = statement.executeQuery(
                    "SELECT memory_type, content, visibility FROM memory "
                        + "WHERE id = '70000000-0000-4000-8000-000000000003'")) {
                    assertThat(rs.next()).isTrue();
                    assertThat(rs.getString("memory_type")).isEqualTo("LIFE_EVENT");
                    assertThat(rs.getString("content")).contains("목포");
                    assertThat(rs.getString("visibility")).isEqualTo("PRIVATE");
                }
            }
        }
    }

    private static int count(Statement statement, String table) throws Exception {
        try (ResultSet rs = statement.executeQuery("SELECT COUNT(*) FROM " + table)) {
            rs.next();
            return rs.getInt(1);
        }
    }

    /** {@code ComposeEnvironmentPassthroughTest} 와 같은 방식으로 저장소 루트를 찾는다. */
    private static Path locate(Path relative) {
        Path here = Path.of("").toAbsolutePath();
        for (Path candidate = here; candidate != null; candidate = candidate.getParent()) {
            Path found = candidate.resolve(relative);
            if (Files.exists(found)) {
                return found;
            }
        }
        throw new IllegalStateException("could not find " + relative + " above " + here);
    }
}
