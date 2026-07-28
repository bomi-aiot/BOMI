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
        new OpenApiSpec("AI Vision Recognition API", "vision-ai.openapi.yaml"),
        new OpenApiSpec("AI Vision Result Callback API", "vision-callback.openapi.yaml"),
        new OpenApiSpec("Conversation and Voice AI API", "voice-ai.openapi.yaml")
    );

    @Autowired
    MockMvc mockMvc;

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
            .andExpect(jsonPath("$['urls.primaryName']").value("BOMI Backend API"))
            .andExpect(jsonPath("$.supportedSubmitMethods").isEmpty())
            .andReturn()
            .getResponse()
            .getContentAsString();

        assertThat(config).contains("BOMI Backend API");
        assertThat(config).contains("/v3/api-docs/bomi-backend");
        for (OpenApiSpec spec : SPECS) {
            assertThat(config).contains(spec.name());
            assertThat(config).contains("/openapi/" + spec.fileName());
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
