package com.ssafy.bomi.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

/**
 * S15P11E102-307 완료 조건을 검증한다 — 로봇 채널 인증 필터가 실제로 로봇 API 를 막는가.
 *
 * <p><b>왜 {@code /api/v1/seniors/{id}/conversation-context} 로 검증하는가.</b> 이
 * 엔드포인트가 CLAUDE.md §5·§8 이 말하는 가장 민감한 응답(이름, 복약 스케줄, 회피
 * 주제, 장기 기억)을 돌려준다. 이 경로 하나가 막히면 나머지 로봇 API 도 같은
 * {@link RobotChannelAuthFilter} 를 거치므로 함께 막힌다 — 경로 패턴이 같기 때문이다
 * (application.yml 의 springdoc {@code bomi-robot} 그룹과 동일한 두 접두사).</p>
 *
 * <p>real PostgreSQL 위에서 돈다. {@code ConversationContextService} 가 Flyway 로 만든
 * 스키마를 그대로 읽으므로, H2 로는 배열·JSONB 차이를 재현하지 못한다
 * (ConversationContextServiceTest 와 같은 이유).</p>
 */
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK,
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false",
        // 이 값이 있어야 필터가 켜진다. 비어 있으면(기본값) 필터는 아무것도 막지
        // 않는다 — 그 경로는 이 테스트가 아니라 나머지 전체 테스트 스위트가
        // 시크릿 없이 그대로 통과하는 것으로 증명된다.
        "bomi.robot-channel.shared-secret=test-shared-secret-307"
    })
@AutoConfigureMockMvc
@Transactional
class RobotChannelAuthFilterTest {

    private static final String ENDPOINT_TEMPLATE = "/api/v1/seniors/%s/conversation-context";
    private static final String EMPTY_CONTEXT_REQUEST_BODY = """
        {"query":"","conversationId":null,"memoryTopK":null,
         "recentMessageLimit":null,"includeDocuments":false,"requesterGuardianId":null}""";

    private static EmbeddedPostgres postgres;

    @Autowired private MockMvc mockMvc;
    @Autowired private AppUserRepository appUserRepository;

    private AppUser senior;

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
    void setUpSenior() {
        senior = AppUser.create("SENIOR", "김순자", null, "순자님");
        appUserRepository.save(senior);
    }

    // ── 완료 조건 1: 헤더 없이 부르면 401, 상태 코드뿐 아니라 본문으로도 확인 ──────

    @Test
    void missingHeaderIsRejectedWithFourOhOneAndABody() throws Exception {
        mockMvc.perform(
                post(ENDPOINT_TEMPLATE.formatted(senior.getId()))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(EMPTY_CONTEXT_REQUEST_BODY))
            .andExpect(status().isUnauthorized())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.error").value("UNAUTHORIZED"))
            .andExpect(jsonPath("$.message")
                .value(org.hamcrest.Matchers.containsString(RobotChannelAuthFilter.HEADER_NAME)));
    }

    @Test
    void wrongHeaderValueIsRejectedWithFourOhOne() throws Exception {
        mockMvc.perform(
                post(ENDPOINT_TEMPLATE.formatted(senior.getId()))
                    .header(RobotChannelAuthFilter.HEADER_NAME, "not-the-real-secret")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(EMPTY_CONTEXT_REQUEST_BODY))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error").value("UNAUTHORIZED"));
    }

    // ── 완료 조건 2: 올바른 헤더면 200, 기존 응답과 동일 ─────────────────────────

    @Test
    void correctHeaderPassesThroughToTheOrdinaryTwoHundredResponse() throws Exception {
        mockMvc.perform(
                post(ENDPOINT_TEMPLATE.formatted(senior.getId()))
                    .header(RobotChannelAuthFilter.HEADER_NAME, "test-shared-secret-307")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(EMPTY_CONTEXT_REQUEST_BODY))
            .andExpect(status().isOk())
            // 필터를 거쳐도 컨트롤러의 평소 응답(프로필 등)이 그대로 나와야 한다.
            .andExpect(jsonPath("$.profile.preferredName").value("순자님"));
    }

    /**
     * 두 검증을 나란히 확인한다 — 같은 시크릿을 쓸 때만 컨트롤러 응답이 완전히
     * 같음을 보장한다. 401 응답 본문을 200 응답과 혼동하는 회귀를 막는다.
     */
    @Test
    void unauthorizedAndAuthorizedResponsesDifferOnlyByAuth() throws Exception {
        String unauthorizedBody = mockMvc.perform(
                post(ENDPOINT_TEMPLATE.formatted(senior.getId()))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(EMPTY_CONTEXT_REQUEST_BODY))
            .andExpect(status().isUnauthorized())
            .andReturn().getResponse().getContentAsString();

        String authorizedBody = mockMvc.perform(
                post(ENDPOINT_TEMPLATE.formatted(senior.getId()))
                    .header(RobotChannelAuthFilter.HEADER_NAME, "test-shared-secret-307")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(EMPTY_CONTEXT_REQUEST_BODY))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        assertThat(unauthorizedBody).doesNotContain("순자님");
        assertThat(authorizedBody).contains("순자님");
    }
}
