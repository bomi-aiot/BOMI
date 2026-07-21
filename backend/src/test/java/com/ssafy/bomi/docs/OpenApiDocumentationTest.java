package com.ssafy.bomi.docs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
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
            .andReturn()
            .getResponse()
            .getContentAsString();

        for (OpenApiSpec spec : SPECS) {
            assertThat(config).contains(spec.name());
            assertThat(config).contains("/openapi/" + spec.fileName());
        }
    }

    @Test
    void swaggerUiAndStaticSpecsAreServed() throws Exception {
        mockMvc.perform(get("/swagger-ui/index.html"))
            .andExpect(status().isOk());

        for (OpenApiSpec spec : SPECS) {
            mockMvc.perform(get("/openapi/" + spec.fileName()))
                .andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.containsString("openapi: 3.0.3")));
        }
    }

    private record OpenApiSpec(String name, String fileName) {}
}
