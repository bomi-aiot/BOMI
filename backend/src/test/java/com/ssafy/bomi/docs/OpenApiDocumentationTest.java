package com.ssafy.bomi.docs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.Map;

import io.swagger.v3.oas.models.OpenAPI;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

@ActiveProfiles("docs")
@AutoConfigureMockMvc
@SpringBootTest
class OpenApiDocumentationTest {
    private static final List<OpenApiSpec> SPECS = List.of(
        new OpenApiSpec("[AI-Vision] 인식 요청 API (계약·미구현)", "vision-ai.openapi.yaml"),
        new OpenApiSpec("[AI-Vision] 결과 Callback API (계약·미구현)", "vision-callback.openapi.yaml"),
        new OpenApiSpec("[AI-Chat] 대화·음성 생성 API (계약·미구현)", "voice-ai.openapi.yaml")
    );

    private static final String PRIMARY_GROUP_NAME = "[BE-Robot] 로봇·AI 채널 API";

    @Autowired
    MockMvc mockMvc;

    @Autowired
    org.springframework.context.ApplicationContext applicationContext;

    @Test
    void openApiYamlFilesAreValidDocuments() throws IOException {
        Yaml yaml = new Yaml(new SafeConstructor(new LoaderOptions()));

        for (OpenApiSpec spec : SPECS) {
            ClassPathResource resource = new ClassPathResource("static/openapi/" + spec.fileName());

            assertThat(resource.exists()).as(spec.fileName()).isTrue();

            try (InputStream inputStream = resource.getInputStream()) {
                byte[] contents = inputStream.readAllBytes();
                Object loaded = yaml.load(new String(contents, java.nio.charset.StandardCharsets.UTF_8));

                assertThat(loaded).as(spec.fileName()).isInstanceOf(Map.class);
                Map<?, ?> document = (Map<?, ?>) loaded;
                assertThat(document.get("openapi")).isEqualTo("3.0.3");
                assertThat(document.get("info")).isInstanceOf(Map.class);
                assertThat(document.get("paths")).isInstanceOf(Map.class);
                assertThat((Map<?, ?>) document.get("paths")).isNotEmpty();

                OpenAPI openApi = io.swagger.v3.core.util.Yaml.mapper()
                    .readValue(contents, OpenAPI.class);
                assertThat(openApi.getInfo()).isNotNull();
                assertThat(openApi.getInfo().getTitle()).isNotBlank();
                assertThat(openApi.getPaths()).isNotEmpty();
                assertThat(openApi.getComponents()).isNotNull();
            }
        }
    }

    @Test
    void swaggerConfigListsEveryStaticSpec() throws Exception {
        String config = mockMvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            // The config also exposes the live backend API group ("bomi-backend") as the
            // primary document alongside the static specs. The exact url count is a springdoc
            // implementation detail (groups may be merged), so assert a lower bound plus the
            // concrete presence of every expected entry below rather than an exact size.
            .andExpect(jsonPath("$.urls.length()")
                .value(org.hamcrest.Matchers.greaterThanOrEqualTo(SPECS.size() + 1)))
            .andExpect(jsonPath("$['urls.primaryName']").value(PRIMARY_GROUP_NAME))
            // Try it out 은 읽기(GET)만 허용된다 (S15P11E102-310). 완전히 빈 배열이면
            // GET 조차 실행할 수 없어 문서의 실용성이 죽고, post/put/delete 가 섞여
            // 있으면 배포 Swagger 에서 그대로 쓰기 API 를 실행할 수 있다 — 정확히
            // ["get"] 하나여야 두 실패를 동시에 막는다.
            .andExpect(jsonPath("$.supportedSubmitMethods").isNotEmpty())
            .andExpect(jsonPath("$.supportedSubmitMethods",
                org.hamcrest.Matchers.contains("get")))
            .andReturn()
            .getResponse()
            .getContentAsString();

        assertThat(config).contains(PRIMARY_GROUP_NAME);
        assertThat(config).contains("/v3/api-docs/bomi-robot");
        assertThat(config).contains("/v3/api-docs/bomi-guardian");
        assertThat(config).contains("/v3/api-docs/bomi-operator");
        assertThat(config).contains("/v3/api-docs/bomi-backend");
        for (OpenApiSpec spec : SPECS) {
            assertThat(config).contains(spec.name());
            assertThat(config).contains("/openapi/" + spec.fileName());
        }
    }

    /**
     * springdoc 은 group-configs 의 그룹을 display-name 으로 이미 드롭다운에 넣는다.
     * 같은 그룹을 swagger-ui.urls 에 또 적으면 항목이 두 번 뜬다.
     */
    @Test
    void dropdownHasNoDuplicateEntries() throws Exception {
        List<String> urls = com.jayway.jsonpath.JsonPath.read(
            mockMvc.perform(get("/v3/api-docs/swagger-config"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString(),
            "$.urls[*].url"
        );

        assertThat(urls).doesNotHaveDuplicates();
    }

    /**
     * 채널이 실제로 갈리는지 본다. 표시명만 바꾸고 {@code paths-to-match} 를 빠뜨리면
     * 드롭다운에는 두 항목이 뜨지만 내용은 똑같은 전체 목록이 된다.
     */
    @Test
    void channelGroupsContainOnlyTheirOwnPaths() throws Exception {
        String robot = mockMvc.perform(get("/v3/api-docs/bomi-robot"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        assertThat(robot)
            .contains("/api/v1/robot/conversation-events")
            .contains("/api/v1/robot/clarifications")
            .contains("/api/v1/robot/guardian-alerts")
            .contains("/api/v1/robot/onboarding")
            .contains("/api/v1/seniors/{seniorId}/conversation-context")
            .contains("/api/v1/seniors/{seniorId}/door-events");
        assertThat(robot)
            .doesNotContain("/api/v1/guardian/")
            .doesNotContain("/api/v1/guardian/walk-requests")
            .doesNotContain("/api/v1/memories")
            .doesNotContain("/api/v1/care-records")
            .doesNotContain("/api/v1/confirmation-requests")
            .doesNotContain("/api/v1/elders")
            .doesNotContain("/api/v1/known-persons");

        String guardian = mockMvc.perform(get("/v3/api-docs/bomi-guardian"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        assertThat(guardian)
            .contains("/api/v1/guardian/")
            .contains("/api/v1/guardian/walk-requests")
            .contains("/api/v1/memories")
            .contains("/api/v1/care-records")
            .contains("/api/v1/confirmation-requests")
            .contains("/api/v1/elders")
            // S15P11E102-260: 명부(known_person) 등록·수정 화면도 가디언웹이 호출한다.
            .contains("/api/v1/known-persons");
        assertThat(guardian).doesNotContain("/api/v1/robot/");

        String operator = mockMvc.perform(get("/v3/api-docs/bomi-operator"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();
        assertThat(operator)
            .contains("/api/v1/operator/robots/{deviceId}/mode-recoveries")
            .doesNotContain("/api/v1/robot/")
            .doesNotContain("/api/v1/guardian/");
    }

    @Test
    void operatorRecoveryPostIsDocumentedAsAuthenticatedSafetyMutation() throws Exception {
        String operator = mockMvc.perform(get("/v3/api-docs/bomi-operator"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        Map<String, Object> recoveryPath = com.jayway.jsonpath.JsonPath.read(
            operator, "$.paths['/api/v1/operator/robots/{deviceId}/mode-recoveries']"
        );
        assertThat(recoveryPath).containsKey("post");

        @SuppressWarnings("unchecked")
        Map<String, Object> post = (Map<String, Object>) recoveryPath.get("post");
        assertThat(post.get("tags")).isEqualTo(List.of("Operator Robot Recovery"));
        assertThat(post.get("security").toString()).contains("operatorSharedSecret");

        @SuppressWarnings("unchecked")
        Map<String, Object> responses = (Map<String, Object>) post.get("responses");
        assertThat(responses).containsKeys("200", "400", "401", "404", "409", "503");

        Map<String, Object> securityScheme = com.jayway.jsonpath.JsonPath.read(
            operator, "$.components.securitySchemes.operatorSharedSecret"
        );
        assertThat(securityScheme)
            .containsEntry("type", "apiKey")
            .containsEntry("in", "header")
            .containsEntry("name", "X-Operator-Shared-Secret");
    }

    /** Guardian WALK is a live POST operation, not merely a matching path prefix. */
    @Test
    void guardianWalkRequestPostIsTaggedAndAppearsOnlyInGuardianGroup() throws Exception {
        String guardian = mockMvc.perform(get("/v3/api-docs/bomi-guardian"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        Map<String, Object> walkPath = com.jayway.jsonpath.JsonPath.read(
            guardian, "$.paths['/api/v1/guardian/walk-requests']"
        );
        assertThat(walkPath).containsKey("post");

        @SuppressWarnings("unchecked")
        Map<String, Object> post = (Map<String, Object>) walkPath.get("post");
        assertThat(post.get("tags"))
            .as("Guardian walk caller tag")
            .isEqualTo(List.of("Guardian Walk"));
        @SuppressWarnings("unchecked")
        Map<String, Object> responses = (Map<String, Object>) post.get("responses");
        assertThat(responses)
            .as("Guardian walk 실제 HTTP 결과 계약")
            .containsKeys("200", "202", "400", "404", "409", "503");

        String robot = mockMvc.perform(get("/v3/api-docs/bomi-robot"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();
        assertThat(robot).doesNotContain("/api/v1/guardian/walk-requests");
    }

    /**
     * S15P11E102-310 — Try it out 의 파괴적 동작(DELETE·PUT 실행)이 응답 "본문"에서
     * 사라졌는지 확인한다.
     *
     * <p>왜 상태 코드가 아니라 본문을 보는가 (CLAUDE.md §26) — 상태 코드만 보면
     * "200 이니까 됐다"고 오판하기 쉽다. supportedSubmitMethods 배열 안에 post·put·
     * patch·delete 가 하나라도 남아 있으면 swagger-ui 는 해당 메서드의 오퍼레이션에
     * "Try it out" / "Execute" 버튼을 그대로 그린다.</p>
     *
     * <p>동시에 문서로서의 가치는 유지돼야 한다 — DELETE·PUT 오퍼레이션 자체가
     * 스펙에서 사라지면 안 된다. 그래서 실제로 DELETE 메서드를 갖고 있는
     * {@code CareRecordController#deleteMedication}(어르신 복약 스케줄 삭제)이
     * bomi-guardian 스펙에 여전히 문서화돼 있는지도 함께 확인한다.</p>
     */
    @Test
    void swaggerTryItOutAllowsOnlyGetAndDocumentationStaysIntact() throws Exception {
        String config = mockMvc.perform(get("/v3/api-docs/swagger-config"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        List<String> submitMethods = com.jayway.jsonpath.JsonPath.read(config, "$.supportedSubmitMethods");
        assertThat(submitMethods)
            .as("Try it out 허용 메서드 — 본문(supportedSubmitMethods), 상태 코드가 아니다")
            .containsExactly("get");
        assertThat(submitMethods).doesNotContain("post", "put", "patch", "delete");

        // 문서 값 자체는 유지된다: 복약 삭제 DELETE 오퍼레이션이 여전히 나열된다.
        String guardian = mockMvc.perform(get("/v3/api-docs/bomi-guardian"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        Map<String, Object> medicationPath = com.jayway.jsonpath.JsonPath.read(
            guardian, "$.paths['/api/v1/care-records/medications/{id}']"
        );
        assertThat(medicationPath)
            .as("복약 스케줄 삭제(DELETE) 오퍼레이션이 문서에서 사라지면 안 된다")
            .containsKey("delete");
        assertThat(medicationPath)
            .as("복약 스케줄 수정(PUT) 오퍼레이션이 문서에서 사라지면 안 된다")
            .containsKey("put");
    }

    /**
     * 새 컨트롤러가 태그 없이 들어오면 여기서 막힌다.
     *
     * <p>규칙을 문서에만 적어두면 다음 컨트롤러는 십중팔구 태그 없이 머지된다. 태그가 없으면
     * springdoc 이 클래스명으로 기본 태그를 만들어 주기 때문에 Swagger 는 멀쩡해 보이고,
     * "이 API 를 누가 호출하는가"라는 정보만 조용히 사라진다.</p>
     */
    @Test
    void everyControllerDeclaresATagNamingItsCaller() {
        Map<String, Object> controllers = applicationContext.getBeansWithAnnotation(
            org.springframework.web.bind.annotation.RestController.class
        );

        List<Class<?>> ours = controllers.values().stream()
            .map(org.springframework.aop.support.AopUtils::getTargetClass)
            // springdoc 자신도 @RestController 로 문서 엔드포인트를 노출한다. 남의 빈이다.
            .filter(type -> type.getPackageName().startsWith("com.ssafy.bomi"))
            .toList();

        assertThat(ours).as("스캔된 컨트롤러").isNotEmpty();

        for (Class<?> type : ours) {
            io.swagger.v3.oas.annotations.tags.Tag tag =
                org.springframework.core.annotation.AnnotationUtils.findAnnotation(
                    type, io.swagger.v3.oas.annotations.tags.Tag.class
                );

            assertThat(tag)
                .as("%s 에 @Tag 가 없다. 호출 주체를 description 에 적어 붙일 것", type.getSimpleName())
                .isNotNull();
            assertThat(tag.name())
                .as("%s 의 @Tag name", type.getSimpleName())
                .isNotBlank();
            assertThat(tag.description())
                .as("%s 의 @Tag description — 누가 호출하는지 적을 것", type.getSimpleName())
                .contains("호출합니다");
        }
    }

    @Test
    void swaggerUiAndStaticSpecsAreServed() throws Exception {
        mockMvc.perform(get("/swagger-ui.html"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/swagger-ui/index.html"));

        mockMvc.perform(get("/swagger-ui/index.html"))
            .andExpect(status().isOk());

        for (OpenApiSpec spec : SPECS) {
            mockMvc.perform(get("/openapi/" + spec.fileName()))
                .andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.containsString("openapi: 3.0.3")));
        }

        // The live backend API group is now generated and served from the application code
        // (springdoc.api-docs.enabled=true + group-configs "bomi-backend").
        mockMvc.perform(get("/v3/api-docs/bomi-backend"))
            .andExpect(status().isOk())
            .andExpect(content().string(org.hamcrest.Matchers.containsString("openapi")));
    }

    @Test
    void visionCallbackSpecListsTheDeployedBackendFirst() throws IOException {
        ClassPathResource resource = new ClassPathResource(
            "static/openapi/vision-callback.openapi.yaml"
        );
        OpenAPI openApi;

        try (InputStream inputStream = resource.getInputStream()) {
            openApi = io.swagger.v3.core.util.Yaml.mapper()
                .readValue(inputStream.readAllBytes(), OpenAPI.class);
        }

        assertThat(openApi.getServers()).isNotEmpty();
        assertThat(openApi.getServers().get(0).getUrl())
            .isEqualTo("https://i15e102.p.ssafy.io");
    }

    private record OpenApiSpec(String name, String fileName) {}
}
