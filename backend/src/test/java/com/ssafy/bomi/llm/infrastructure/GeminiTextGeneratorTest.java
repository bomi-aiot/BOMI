package com.ssafy.bomi.llm.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.llm.application.TextGenerator.GenerationFailedException;
import com.ssafy.bomi.llm.config.LlmProperties;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * {@code GeminiTextGenerator} against a local stand-in HTTP server, not the real Gemini API.
 *
 * <p><b>왜 실제 API 를 부르지 않는가.</b> 이 클라이언트도 과금 대상이다. 실제 왕복이
 * 필요한 단 하나의 질문("Gemini 가 진짜 이 모양으로 응답하는가")은
 * {@code UpstageEmbeddingBilledTest} 와 같은 자리에 놓을 별도의 {@code @Tag("billed")}
 * 테스트의 몫이고, 이 파일이 검증하는 것(요청 조립·헤더·응답 파싱·예외 변환)은 전부
 * 결정적 가짜 서버로 무료로 확인할 수 있다.</p>
 *
 * <p>{@code com.sun.net.httpserver.HttpServer} 는 JDK 내장이라 새 테스트 의존성을
 * 추가하지 않는다 — 이 프로젝트에 아직 MockWebServer/WireMock 이 없다.</p>
 */
class GeminiTextGeneratorTest {

    private HttpServer server;
    private LlmProperties properties;

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.start();

        properties = new LlmProperties();
        properties.setEnabled(true);
        properties.setApiKey("test-key");
        properties.setModel("test-model");
        properties.setTimeoutMillis(2_000);
        properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
    }

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void generateReturnsTheJoinedCandidateTextAndSendsTheApiKeyHeader() {
        AtomicReference<String> capturedHeader = new AtomicReference<>();
        AtomicReference<String> capturedPath = new AtomicReference<>();
        respondWith(exchange -> {
            capturedHeader.set(exchange.getRequestHeaders().getFirst("x-goog-api-key"));
            capturedPath.set(exchange.getRequestURI().getPath());
            return """
                {"candidates":[{"content":{"parts":[{"text":"짧은 요약입니다."}]}}]}
                """;
        });

        GeminiTextGenerator generator = new GeminiTextGenerator(properties);
        String result = generator.generate("이 대화를 요약해줘");

        assertThat(result).isEqualTo("짧은 요약입니다.");
        assertThat(capturedHeader.get()).isEqualTo("test-key");
        assertThat(capturedPath.get()).isEqualTo("/v1beta/models/test-model:generateContent");
        assertThat(generator.billedCallCount()).isEqualTo(1);
    }

    @Test
    void multiplePartsAreJoinedWithASpace() {
        respondWith(exchange -> """
            {"candidates":[{"content":{"parts":[{"text":"첫 문장."},{"text":"둘째 문장."}]}}]}
            """);

        GeminiTextGenerator generator = new GeminiTextGenerator(properties);

        assertThat(generator.generate("프롬프트")).isEqualTo("첫 문장. 둘째 문장.");
    }

    @Test
    void noCandidatesBecomesAGenerationFailedException() {
        respondWith(exchange -> "{\"candidates\":[]}");

        GeminiTextGenerator generator = new GeminiTextGenerator(properties);

        assertThatThrownBy(() -> generator.generate("프롬프트"))
            .isInstanceOf(GenerationFailedException.class);
    }

    @Test
    void aServerErrorBecomesAGenerationFailedExceptionRatherThanLeaking() {
        server.createContext("/v1beta/models/test-model:generateContent", exchange -> {
            byte[] body = "boom".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(500, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });

        GeminiTextGenerator generator = new GeminiTextGenerator(properties);

        assertThatThrownBy(() -> generator.generate("프롬프트"))
            .isInstanceOf(GenerationFailedException.class);
    }

    @Test
    void blankPromptIsRefusedWithoutCallingTheNetwork() {
        respondWith(exchange -> """
            {"candidates":[{"content":{"parts":[{"text":"불렸으면 안 된다"}]}}]}
            """);

        GeminiTextGenerator generator = new GeminiTextGenerator(properties);

        assertThatThrownBy(() -> generator.generate("   "))
            .isInstanceOf(GenerationFailedException.class);
        assertThat(generator.billedCallCount())
            .as("빈 프롬프트는 과금 호출로 세지 않는다")
            .isZero();
    }

    @Test
    void isAvailableFollowsUsability() {
        GeminiTextGenerator usable = new GeminiTextGenerator(properties);
        assertThat(usable.isAvailable()).isTrue();

        properties.setApiKey("");
        GeminiTextGenerator unusable = new GeminiTextGenerator(properties);
        assertThat(unusable.isAvailable()).isFalse();
        assertThatThrownBy(() -> unusable.generate("프롬프트"))
            .isInstanceOf(GenerationFailedException.class);
    }

    /** Registers a 200-OK JSON responder at the exact path this client calls. */
    private void respondWith(JsonBody body) {
        server.createContext("/v1beta/models/test-model:generateContent", exchange -> {
            byte[] payload = body.render(exchange).getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, payload.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(payload);
            }
        });
    }

    @FunctionalInterface
    private interface JsonBody {
        String render(HttpExchange exchange) throws IOException;
    }
}
