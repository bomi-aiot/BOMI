package com.ssafy.bomi.seed;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.context.api.ConversationContextRequest;
import com.ssafy.bomi.context.api.ConversationContextResponse;
import com.ssafy.bomi.context.application.ConversationContextService;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.Statement;
import java.util.UUID;
import javax.sql.DataSource;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 완료 조건 확인: "온보딩을 마친 김순자 시드로 문맥 API 를 호출하면 memories 에 회상
 * 씨앗이 실려 옵니다" (S15P11E102-262).
 *
 * <p>{@code @Transactional} 을 일부러 클래스에 붙이지 않는다 — seed 스크립트가 자체
 * {@code BEGIN}/{@code COMMIT} 을 갖고 있어서, 스프링이 감싼 트랜잭션 안에서
 * 실행하면 커밋 시점이 꼬인다. 그 대신 스프링이 관리하는 {@link DataSource} 를 그대로
 * 받아 seed 스크립트를 psql 과 같은 방식으로 한 번 실행하고, 조회는
 * {@link ConversationContextService#assemble} 자신의(이번 티켓에서 readOnly 를 뺀)
 * 트랜잭션에 맡긴다.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false"
    })
class SeedKimSunjaContextIntegrationTest {

    private static final UUID KIM_SUNJA_ID = UUID.fromString("10000000-0000-4000-8000-000000000001");

    private static EmbeddedPostgres postgres;

    @Autowired private ConversationContextService contextService;
    @Autowired private DataSource dataSource;

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

    @Test
    void contextApiSurfacesReminiscenceSeedsForTheOnboardedSeed() throws Exception {
        applySeedScript();

        // query 를 비워 둔다 — 회상 씨앗은 아직 대화에 한 번도 안 쓰였으니, 관련성이
        // 아니라 importance·recency 만으로도 top-10 안에 들어와야 완료 조건이 뜻하는
        // "실려 옵니다"가 참이다.
        ConversationContextResponse context = contextService.assemble(
            KIM_SUNJA_ID, new ConversationContextRequest("", null, 10, null, false, null));

        assertThat(context.memories())
            .extracting(ConversationContextResponse.MemoryItem::content)
            .anySatisfy(content -> assertThat(content).contains("목포"));
    }

    private void applySeedScript() throws Exception {
        String sql = Files.readString(
            locate(Path.of("scripts", "dev", "seed-kim-sunja.sql")), StandardCharsets.UTF_8);
        try (Connection connection = dataSource.getConnection();
            Statement statement = connection.createStatement()) {
            statement.execute(sql);
        }
    }

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
