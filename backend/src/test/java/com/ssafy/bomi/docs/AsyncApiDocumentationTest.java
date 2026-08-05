package com.ssafy.bomi.docs;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

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

/**
 * MQTT 계약이 스펙으로 살아 있는지 확인한다.
 *
 * <p>가장 중요한 검사는 {@code everyDocumentedTopicExistsInTheMarkdownContract} 다.
 * 이 스펙은 최종 기준인 {@code docs/mqtt/scenario-contract-v1.md} 의 메시지 형식을
 * 표현하므로, 한쪽만 고치면 팀은 서로 다른 두 계약서를 보게 된다.</p>
 */
@ActiveProfiles("docs")
@AutoConfigureMockMvc
@SpringBootTest
class AsyncApiDocumentationTest {

    private static final String SPEC_RESOURCE = "static/openapi/bomi-mqtt.asyncapi.yaml";

    private static final List<String> TOPIC_ADDRESSES = List.of(
        "bomi/v1/iot/{sourceId}/events",
        "bomi/v1/robot/{robotId}/commands",
        "bomi/v1/ai/{robotId}/commands",
        "bomi/v1/robot/{robotId}/events",
        "bomi/v1/robot/{robotId}/status",
        "bomi/v1/robot/{robotId}/results"
    );

    private static final List<String> SCENARIO_MESSAGES = List.of(
        "DoorOpened",
        "AmbientEnvironmentObserved",
        "Navigate",
        "Speak",
        "FollowStart",
        "FollowStop",
        "StartConversation",
        "WakeWordDetected",
        "WalkRequested",
        "ConversationStarted",
        "ConversationEnded",
        "NavigationResult",
        "SpeakResult",
        "CancelResult",
        "FollowResult"
    );

    @Autowired
    MockMvc mockMvc;

    @SuppressWarnings("unchecked")
    private Map<String, Object> loadSpec() throws IOException {
        try (InputStream in = new ClassPathResource(SPEC_RESOURCE).getInputStream()) {
            Yaml yaml = new Yaml(new SafeConstructor(new LoaderOptions()));
            return (Map<String, Object>) yaml.load(
                new String(in.readAllBytes(), StandardCharsets.UTF_8)
            );
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void specIsAValidAsyncApiDocument() throws IOException {
        Map<String, Object> spec = loadSpec();

        assertThat(spec.get("asyncapi")).isEqualTo("3.0.0");
        assertThat((Map<String, Object>) spec.get("info")).containsKeys("title", "version");
        assertThat((Map<String, Object>) spec.get("channels")).isNotEmpty();
        assertThat((Map<String, Object>) spec.get("operations")).isNotEmpty();

        Map<String, Object> components = (Map<String, Object>) spec.get("components");
        assertThat((Map<String, Object>) components.get("messages")).isNotEmpty();
        assertThat((Map<String, Object>) components.get("schemas")).isNotEmpty();
    }

    @Test
    @SuppressWarnings("unchecked")
    void everyTopicFromTheContractIsDocumented() throws IOException {
        Map<String, Object> channels = (Map<String, Object>) loadSpec().get("channels");

        List<String> addresses = channels.values().stream()
            .map(channel -> (String) ((Map<String, Object>) channel).get("address"))
            .toList();

        assertThat(addresses).containsExactlyInAnyOrderElementsOf(TOPIC_ADDRESSES);
    }

    @Test
    @SuppressWarnings("unchecked")
    void everyScenarioMessageHasAnExample() throws IOException {
        Map<String, Object> components =
            (Map<String, Object>) loadSpec().get("components");
        Map<String, Object> messages =
            (Map<String, Object>) components.get("messages");

        for (String messageName : SCENARIO_MESSAGES) {
            assertThat(messages)
                .as("5개 시나리오에서 사용하는 %s 메시지가 없다", messageName)
                .containsKey(messageName);

            Map<String, Object> message =
                (Map<String, Object>) messages.get(messageName);
            assertThat((List<Object>) message.get("examples"))
                .as("%s 메시지 예시가 없다", messageName)
                .isNotEmpty();
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void wakeWordSchemaMatchesTheRuntimeWireValidation() throws IOException {
        Map<String, Object> components =
            (Map<String, Object>) loadSpec().get("components");
        Map<String, Object> schemas =
            (Map<String, Object>) components.get("schemas");

        Map<String, Object> robotId = (Map<String, Object>) schemas.get("RobotId");
        assertThat(robotId)
            .containsEntry("minLength", 1)
            .containsEntry("maxLength", 64)
            .containsEntry("pattern", "^[A-Za-z0-9._-]{1,64}$");

        Map<String, Object> wake =
            (Map<String, Object>) schemas.get("WakeWordDetectedPayload");
        assertThat(wake.get("additionalProperties")).isEqualTo(false);
        assertThat((List<String>) wake.get("required"))
            .containsExactly("eventId", "robotId", "type", "occurredAt", "payload");

        Map<String, Object> properties =
            (Map<String, Object>) wake.get("properties");
        Map<String, Object> payload =
            (Map<String, Object>) properties.get("payload");
        assertThat(payload.get("additionalProperties")).isEqualTo(false);
        assertThat((List<String>) payload.get("required")).containsExactly("keyword");
    }

    /**
     * 스펙과 마크다운 계약서가 같은 토픽을 말하는지 본다. 토픽을 하나 추가하면서
     * 한쪽만 고치면 여기서 걸린다.
     */
    @Test
    void everyDocumentedTopicExistsInTheMarkdownContract() throws IOException {
        Path markdown = Path.of("..", "docs", "mqtt", "scenario-contract-v1.md");
        assertThat(Files.exists(markdown))
            .as("docs/mqtt/scenario-contract-v1.md — 시나리오 메시지 최종 기준")
            .isTrue();

        String contract = Files.readString(markdown, StandardCharsets.UTF_8);

        for (String address : TOPIC_ADDRESSES) {
            assertThat(contract)
                .as("%s 가 마크다운 계약서에 없다. 두 문서가 갈라졌다", address)
                .contains(address);
        }
    }

    /** 모든 $ref 가 실제로 가리키는 대상이 있는지 본다. 렌더러는 깨진 참조를 조용히 비운다. */
    @Test
    void everyInternalReferenceResolves() throws IOException {
        Map<String, Object> spec = loadSpec();
        assertThat(collectBrokenRefs(spec, spec)).isEmpty();
    }

    @SuppressWarnings("unchecked")
    private List<String> collectBrokenRefs(Map<String, Object> root, Object node) {
        if (node instanceof Map<?, ?> map) {
            Object ref = map.get("$ref");
            if (ref instanceof String pointer && !resolves(root, pointer)) {
                return List.of(pointer);
            }
            return map.values().stream()
                .flatMap(value -> collectBrokenRefs(root, value).stream())
                .toList();
        }
        if (node instanceof List<?> list) {
            return list.stream()
                .flatMap(value -> collectBrokenRefs(root, value).stream())
                .toList();
        }
        return List.of();
    }

    @SuppressWarnings("unchecked")
    private boolean resolves(Map<String, Object> root, String pointer) {
        if (!pointer.startsWith("#/")) {
            return false;
        }
        Object current = root;
        for (String segment : pointer.substring(2).split("/")) {
            if (!(current instanceof Map)) {
                return false;
            }
            current = ((Map<String, Object>) current).get(segment);
            if (current == null) {
                return false;
            }
        }
        return true;
    }

    @Test
    void specIsServedAsYamlAndAsJson() throws Exception {
        mockMvc.perform(get("/openapi/bomi-mqtt.asyncapi.yaml"))
            .andExpect(status().isOk());

        mockMvc.perform(get("/openapi/bomi-mqtt.asyncapi.json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.asyncapi").value("3.0.0"))
            .andExpect(jsonPath("$.channels.robotCommands.address")
                .value("bomi/v1/robot/{robotId}/commands"))
            .andExpect(jsonPath("$.channels.aiCommands.address")
                .value("bomi/v1/ai/{robotId}/commands"));
    }

    /** 뷰어는 외부 리소스를 쓰지 않아야 한다. 운영 CSP 가 script-src 'self' 다. */
    @Test
    void viewerIsServedAndSelfContained() throws Exception {
        String mqtt = mockMvc.perform(get("/asyncapi/mqtt/index.html"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();
        String websocket = mockMvc.perform(get("/asyncapi/websocket/index.html"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();
        String landing = mockMvc.perform(get("/docs/index.html"))
            .andExpect(status().isOk())
            .andReturn().getResponse().getContentAsString();

        mockMvc.perform(get("/asyncapi/mqtt/renderer.js")).andExpect(status().isOk());
        mockMvc.perform(get("/asyncapi/style.css")).andExpect(status().isOk());

        for (String page : List.of(mqtt, websocket)) {
            assertThat(page)
                .as("뷰어가 외부 호스트를 참조하면 운영 CSP 에서 차단된다")
                .doesNotContain("http://")
                .doesNotContain("https://");
        }

        // 랜딩은 실제 통신 주소를 안내해야 해서 https 문자열을 포함한다. 대신 외부
        // 리소스를 끌어오지 않는지만 본다.
        assertThat(landing).doesNotContain("<script");
        assertThat(landing).doesNotContain("//unpkg").doesNotContain("//cdn");
    }

    /**
     * 게시하는 주소는 디렉터리 URL 이다. Spring 은 중첩 디렉터리의 index.html 을
     * 자동으로 내려주지 않으므로(루트만 해 준다) 명시적으로 이어줘야 한다.
     */
    @Test
    void directoryUrlsServeTheirIndexPage() throws Exception {
        for (String base : List.of("/docs", "/asyncapi/mqtt", "/asyncapi/websocket")) {
            mockMvc.perform(get(base))
                .andExpect(status().isOk());
            mockMvc.perform(get(base + "/"))
                .andExpect(status().isOk());
        }
    }

    /** 세 문서가 서로 오갈 수 있어야 진입점이 하나라고 말할 수 있다. */
    @Test
    void everyDocPageLinksToTheOthers() throws Exception {
        String landing = mockMvc.perform(get("/docs/index.html"))
            .andReturn().getResponse().getContentAsString();
        assertThat(landing)
            .contains("/swagger-ui.html")
            .contains("/asyncapi/mqtt/")
            .contains("/asyncapi/websocket/");

        String mqtt = mockMvc.perform(get("/asyncapi/mqtt/index.html"))
            .andReturn().getResponse().getContentAsString();
        assertThat(mqtt).contains("/docs/").contains("/swagger-ui.html");

        String websocket = mockMvc.perform(get("/asyncapi/websocket/index.html"))
            .andReturn().getResponse().getContentAsString();
        assertThat(websocket).contains("/docs/").contains("/asyncapi/mqtt/");
    }
}
