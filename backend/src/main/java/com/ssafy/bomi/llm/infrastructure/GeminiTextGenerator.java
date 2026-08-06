package com.ssafy.bomi.llm.infrastructure;

import com.ssafy.bomi.llm.application.TextGenerator;
import com.ssafy.bomi.llm.config.LlmProperties;
import jakarta.annotation.PostConstruct;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/**
 * GMS(SSAFY 사내 게이트웨이)를 경유한 Gemini 텍스트 생성 어댑터 (S15P11E102-254).
 *
 * <p><b>이 백엔드 최초의 생성형 LLM 호출이다(§28 사용자 승인 완료).</b> 지금까지 백엔드가
 * 부르는 유일한 외부 AI 는 Qdrant(검색)와 Upstage(임베딩, 고정 출력 형태) 뿐이었다. 이
 * 클라이언트는 자유 형식 텍스트를 만들어 {@code conversation_summary.content} 에 저장하고,
 * 나중에 다시 프롬프트로 먹인다 — CLAUDE.md §16 이 말하는 "생성 호출"이 바로 이것이라,
 * 호출하는 쪽(스윕 잡)이 한 번의 스윕에 여러 번 부르더라도 한 대화당 한 번만 부른다.</p>
 *
 * <p><b>{@code UpstageEmbeddingClient} 와 같은 관례를 그대로 따른다.</b> 과금 카운터를
 * 로그로 노출하고, 기동 시 ON/OFF·상한을 한 줄 로그로 남기고, 재시도는 하지 않는다(다음
 * 스윕이 재시도 역할을 한다).</p>
 *
 * <p><b>로봇 쪽 {@code llm/client.py} 와 같은 게이트웨이·같은 계정을 쓴다.</b> 엔드포인트
 * 모양({@code /v1beta/models/{model}:generateContent}), 인증 헤더({@code x-goog-api-key})가
 * 로봇 쪽과 동일하다 — 두 채널이 이미 검증된 같은 경로를 재사용하는 것이지, 새로 발명한
 * 프로토콜이 아니다.</p>
 */
@Component
public class GeminiTextGenerator implements TextGenerator {

    private static final Logger log = LoggerFactory.getLogger(GeminiTextGenerator.class);

    private final LlmProperties properties;
    private final RestClient restClient;

    /** Billed calls made since boot. Logged so a runaway loop is visible in the log. */
    private final AtomicLong callCount = new AtomicLong();

    public GeminiTextGenerator(LlmProperties properties) {
        this.properties = properties;

        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        Duration timeout = Duration.ofMillis(properties.getTimeoutMillis());
        factory.setConnectTimeout(timeout);
        factory.setReadTimeout(timeout);

        this.restClient = RestClient.builder()
            .baseUrl(properties.getBaseUrl())
            .requestFactory(factory)
            .build();
    }

    @PostConstruct
    void announce() {
        if (properties.isUsable()) {
            log.info("llm generation ON: model={} (metered API — sweep cap {} calls/run)",
                properties.getModel(), properties.getMaxCallsPerRun());
            return;
        }
        // ★ 조용히 넘어가지 않는다. 대화 요약이 꺼진 것은 지원되는 상태이지만 '의도한
        //   것'이어야 한다. 로그가 없으면 몇 주 뒤 "로봇이 지난 대화를 전혀 기억 못
        //   한다"는 증상으로만 발견된다.
        log.warn("llm generation OFF ({}): conversation summaries will not be generated "
                + "(S15P11E102-254)",
            properties.isEnabled() ? "no GEMINI_API_KEY" : "bomi.llm.enabled=false");
    }

    @Override
    public boolean isAvailable() {
        return properties.isUsable();
    }

    @Override
    public String generate(String prompt) {
        if (!isAvailable()) {
            throw new GenerationFailedException("llm generation is not configured");
        }
        if (prompt == null || prompt.isBlank()) {
            throw new GenerationFailedException("refusing to generate from a blank prompt");
        }

        long callNumber = callCount.incrementAndGet();
        try {
            GenerateContentResponse response = restClient.post()
                .uri("/v1beta/models/{model}:generateContent", properties.getModel())
                .header("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                .header("x-goog-api-key", properties.getApiKey())
                .body(Map.of(
                    "contents", List.of(Map.of("parts", List.of(Map.of("text", prompt)))),
                    "generationConfig", Map.of("maxOutputTokens", properties.getMaxOutputTokens())))
                .retrieve()
                .body(GenerateContentResponse.class);

            String text = firstText(response);
            log.debug("generated {} chars from a {}-char prompt with {} (billed call #{})",
                text.length(), prompt.length(), properties.getModel(), callNumber);
            return text;
        } catch (GenerationFailedException error) {
            throw error;
        } catch (Exception error) {
            throw new GenerationFailedException(
                "generation call #%d to %s failed".formatted(callNumber, properties.getModel()),
                error);
        }
    }

    /**
     * {@code candidates[0].content.parts[*].text} 를 이어붙이고 다듬는다.
     *
     * <p>파트가 여러 개로 쪼개져 오는 경우를 대비한다 — 로봇 쪽 파서와 같은 가정이다.
     * 빈 결과는 여기서 예외로 바꾼다: 호출은 이미 과금됐는데 저장할 내용이 없으면,
     * 그 사실을 호출부가 null 체크로 놓치게 두는 것보다 실패로 명확히 하는 편이 낫다.</p>
     */
    private String firstText(GenerateContentResponse response) {
        if (response == null || response.candidates() == null || response.candidates().isEmpty()) {
            throw new GenerationFailedException("model returned no candidates");
        }
        Candidate candidate = response.candidates().get(0);
        if (candidate == null || candidate.content() == null || candidate.content().parts() == null) {
            throw new GenerationFailedException("candidate has no content parts");
        }
        String joined = candidate.content().parts().stream()
            .map(Part::text)
            .filter(text -> text != null && !text.isBlank())
            .reduce("", (a, b) -> a.isBlank() ? b : a + " " + b)
            .strip();
        if (joined.isBlank()) {
            throw new GenerationFailedException("model returned an empty response");
        }
        return joined;
    }

    /** How many billed calls this process has made. Read by tests. */
    public long billedCallCount() {
        return callCount.get();
    }

    /**
     * Gemini {@code generateContent} 응답 중 이 클라이언트가 실제로 쓰는 부분만 선언한다.
     *
     * <p>{@code safetyRatings}, {@code finishReason} 등 나머지 필드는 지금 아무도 읽지
     * 않으므로 선언하지 않는다 — Jackson 은 알 수 없는 필드를 기본적으로 무시한다.</p>
     */
    private record GenerateContentResponse(List<Candidate> candidates) {}

    private record Candidate(Content content) {}

    private record Content(List<Part> parts) {}

    private record Part(String text) {}
}
