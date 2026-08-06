package com.ssafy.bomi.e2e;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.abort;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.embedding.application.EmbeddingClient;
import com.ssafy.bomi.embedding.application.EmbeddingSyncService;
import com.ssafy.bomi.embedding.application.EmbeddingSyncService.SyncReport;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.fact.domain.FactCandidateStatus;
import com.ssafy.bomi.fact.repository.FactCandidateRepository;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import jakarta.persistence.EntityManager;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * AI 프로세스부터 PostgreSQL/Qdrant 재색인까지 잇는 무료 교차 모듈 E2E.
 *
 * <p>Python 쪽 생성 LLM과 TTS만 결정적 대역이다. 문맥 조회, 대화 적재, 사실 후보
 * 제출은 실제 {@code Backend*Client}가 이 테스트의 무작위 HTTP 포트를 호출한다.
 * 백엔드는 실제 PostgreSQL과 실제 Qdrant를 사용한다. 따라서 단위 테스트가 놓치는
 * URL, JSON 이름, 트랜잭션, 검색 컬렉션, 프롬프트 전달 경계가 모두 한 번에 검증된다.</p>
 *
 * <p>실행에는 Qdrant와 AI 소스/가상환경 위치가 필요하다. 없으면 초록으로 위장하지
 * 않고 중단(abort)한다.</p>
 */
@Tag("integration")
@DisplayName("AI → Backend → PostgreSQL/Qdrant → AI 교차 모듈 RAG E2E")
@SpringBootTest(
    webEnvironment = WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false",
        "bomi.embedding.sync-enabled=false",
        "bomi.embedding.sync-batch-size=30",
        "bomi.conversation-lifecycle.sweep-enabled=false",
        "bomi.llm.enabled=false"
    })
@Import(CrossModuleRagEndToEndIntegrationTest.DeterministicEmbeddingConfig.class)
class CrossModuleRagEndToEndIntegrationTest {

    private static final int DIMENSIONS = 4096;
    private static EmbeddedPostgres postgres;

    @LocalServerPort private int port;
    @TempDir Path tempDir;

    @Autowired AppUserRepository appUserRepository;
    @Autowired ConversationRepository conversationRepository;
    @Autowired ConversationMessageRepository messageRepository;
    @Autowired ConversationSummaryRepository summaryRepository;
    @Autowired FactCandidateRepository factCandidateRepository;
    @Autowired MemoryRepository memoryRepository;
    @Autowired EmbeddingSyncService embeddingSyncService;
    @Autowired EntityManager entityManager;
    @Autowired ObjectMapper objectMapper;

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
    static void runtimeProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> postgres.getJdbcUrl("postgres", "postgres"));
        registry.add("spring.datasource.username", () -> "postgres");
        registry.add("spring.datasource.password", () -> "");
        registry.add("spring.datasource.driver-class-name", () -> "org.postgresql.Driver");
        registry.add("bomi.qdrant.host",
            () -> System.getProperty("bomi.test.qdrant.host", ""));
        registry.add("bomi.qdrant.grpc-port",
            () -> System.getProperty("bomi.test.qdrant.grpcPort", "6334"));
        registry.add("bomi.qdrant.dimensions", () -> DIMENSIONS);
        registry.add("bomi.qdrant.timeout-millis", () -> 10_000);
        registry.add("bomi.embedding.dimensions", () -> DIMENSIONS);
    }

    @Test
    @DisplayName("복지 문서와 과거 요약이 프롬프트에 도달하고 추출 기억이 재색인 후 회상된다")
    void conversationExtractionMaterializationAndRecallCrossTheRealModuleBoundary()
        throws Exception {
        requireExternalTestRuntime();

        AppUser senior = AppUser.create("SENIOR", "교차 E2E 어르신", null, "어르신");
        senior.changePersonalizationConsent(ConsentStatus.GRANTED);
        senior.changeHealthDataConsent(ConsentStatus.GRANTED);
        senior.changeScheduleConsent(ConsentStatus.GRANTED);
        senior = appUserRepository.saveAndFlush(senior);
        UUID seniorId = senior.getId();

        Conversation priorConversation = conversationRepository.saveAndFlush(
            Conversation.open(seniorId));
        ConversationSummary priorSummary = summaryRepository.saveAndFlush(
            ConversationSummary.forConversation(
                seniorId, priorConversation.getId(),
                OffsetDateTime.now().minusDays(2), OffsetDateTime.now().minusDays(2).plusMinutes(5),
                "지난 대화에서 뜨개질 모임 이야기를 나눴다", 2));

        SyncReport initialSync = embeddingSyncService.syncDue();
        assertThat(initialSync.summariesIndexed()).isEqualTo(1);
        assertThat(initialSync.memoriesIndexed()).isZero();
        assertThat(summaryRepository.findById(priorSummary.getId()).orElseThrow()
            .getEmbeddingStatus()).isEqualTo(EmbeddingStatus.SYNCED);

        JsonNode conversationPhase = runAiDriver("conversation", seniorId);

        assertThat(conversationPhase.path("turns").get(0).path("intent").asText())
            .isEqualTo("info");
        assertThat(conversationPhase.path("turns").get(0)
            .path("retrieval").path("documents_requested").asBoolean()).isTrue();
        assertThat(conversationPhase.path("turns").get(0)
            .path("retrieval").path("document_used").asBoolean()).isTrue();
        assertThat(conversationPhase.path("turns").get(0).path("documentCount").asInt())
            .isGreaterThan(0);
        assertThat(conversationPhase.path("prompts").get(0).asText())
            .contains("복지로", "출처=", "청크=", "인용=", "URL=https://www.bokjiro.go.kr");
        assertThat(conversationPhase.path("extraction").path("processed").asInt())
            .isEqualTo(2);
        assertThat(conversationPhase.path("extraction").path("submitted").asInt())
            .isEqualTo(1);
        assertThat(conversationPhase.path("extraction").path("failed").asInt()).isZero();

        entityManager.clear();
        List<Conversation> conversations = conversationRepository.findAll().stream()
            .filter(item -> item.getSeniorId().equals(seniorId))
            .toList();
        assertThat(conversations).hasSize(2); // 사전 요약용 1건 + AI가 이어 쓴 대화 1건
        assertThat(messageRepository.findAll()).hasSize(4); // 두 턴 × SENIOR/ROBOT

        assertThat(factCandidateRepository.findAll())
            .singleElement()
            .satisfies(candidate -> {
                assertThat(candidate.getSeniorId()).isEqualTo(seniorId);
                assertThat(candidate.getStatus()).isEqualTo(FactCandidateStatus.MATERIALIZED);
                assertThat(candidate.getFactType()).isEqualTo("HOBBY");
            });

        List<Memory> materialized = memoriesFor(seniorId);
        assertThat(materialized)
            .singleElement()
            .satisfies(memory -> {
                assertThat(memory.getContent()).isEqualTo("요즘 뜨개질을 자주 한다");
                assertThat(memory.getEmbeddingStatus()).isEqualTo(EmbeddingStatus.PENDING);
            });

        SyncReport reindex = embeddingSyncService.syncDue();
        assertThat(reindex.memoriesIndexed()).isEqualTo(1);
        assertThat(reindex.summariesIndexed()).isZero();
        entityManager.clear();
        assertThat(memoriesFor(seniorId))
            .singleElement()
            .satisfies(memory ->
                assertThat(memory.getEmbeddingStatus()).isEqualTo(EmbeddingStatus.SYNCED));

        JsonNode recallPhase = runAiDriver("recall", seniorId);
        JsonNode recallTurn = recallPhase.path("turns").get(0);
        assertThat(recallTurn.path("retrieval").path("semantic_requested").asBoolean()).isTrue();
        assertThat(recallTurn.path("retrieval").path("semantic_used").asBoolean()).isTrue();
        assertThat(recallTurn.path("retrieval").path("hit_count").asInt()).isGreaterThan(0);
        assertThat(recallTurn.path("memoryCount").asInt()).isGreaterThan(0);
        assertThat(recallTurn.path("summaryCount").asInt()).isGreaterThan(0);
        assertThat(recallPhase.path("prompts").get(0).asText())
            .contains("요즘 뜨개질을 자주 한다", "지난 대화에서 뜨개질 모임 이야기를 나눴다");
    }

    private void requireExternalTestRuntime() {
        if (System.getProperty("bomi.test.qdrant.host", "").isBlank()) {
            abort("QDRANT_HOST가 없습니다. 실제 Qdrant 없이 교차 E2E를 통과로 처리하지 않습니다.");
        }
        if (System.getProperty("bomi.test.ai.python", "").isBlank()
            || System.getProperty("bomi.test.ai.dir", "").isBlank()) {
            abort("BOMI_AI_PYTHON/BOMI_AI_CHAT_DIR가 없습니다. AI 프로세스 경계를 "
                + "건너뛰고 교차 E2E를 통과로 처리하지 않습니다.");
        }
    }

    private JsonNode runAiDriver(String phase, UUID seniorId) throws Exception {
        Path aiChatDir = Path.of(System.getProperty("bomi.test.ai.dir")).toAbsolutePath();
        Path driver = aiChatDir.resolve("tests/cross_module_rag_driver.py");
        Path source = aiChatDir.resolve("src");
        Path stderr = tempDir.resolve("ai-" + phase + ".stderr.log");
        Path localstore = tempDir.resolve("localstore");

        assertThat(driver).isRegularFile();
        assertThat(source).isDirectory();

        ProcessBuilder builder = new ProcessBuilder(
            System.getProperty("bomi.test.ai.python"),
            driver.toString(),
            "--phase", phase);
        builder.directory(aiChatDir.toFile());
        builder.redirectError(stderr.toFile());
        Map<String, String> environment = builder.environment();
        environment.put("PYTHONPATH", source.toString());
        environment.put("BACKEND_BASE_URL", "http://127.0.0.1:" + port);
        environment.put("BACKEND_TIMEOUT_SECONDS", "5");
        environment.put("HTTP_MAX_ATTEMPTS", "1");
        environment.put("HTTP_BACKOFF_SECONDS", "0");
        environment.put("HTTP_MAX_BACKOFF_SECONDS", "0");
        environment.put("LOCALSTORE_DIR", localstore.toString());
        environment.put("SENIOR_ID", seniorId.toString());
        environment.put("AUDIO_MODE", "laptop");
        environment.put("WAKEWORD_ENABLED", "false");
        environment.put("MQTT_ENABLED", "false");
        environment.put("USE_GRAPH_RUNTIME", "true");
        environment.put("PYTHONUTF8", "1");
        environment.put("PYTHONIOENCODING", "utf-8");

        Process process = builder.start();
        String stdout = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        boolean completed = process.waitFor(45, TimeUnit.SECONDS);
        if (!completed) {
            process.destroyForcibly();
        }
        String errors = Files.exists(stderr)
            ? new String(Files.readAllBytes(stderr), StandardCharsets.UTF_8)
            : "";

        assertThat(completed)
            .withFailMessage("AI %s 단계가 45초 안에 끝나지 않았습니다. stderr=%s", phase, errors)
            .isTrue();
        assertThat(process.exitValue())
            .withFailMessage("AI %s 단계가 실패했습니다. stdout=%s stderr=%s", phase, stdout, errors)
            .isZero();
        assertThat(stdout).as("AI driver JSON output").isNotBlank();
        return objectMapper.readTree(stdout.trim());
    }

    private List<Memory> memoriesFor(UUID seniorId) {
        return memoryRepository.findAll().stream()
            .filter(memory -> memory.getSeniorId().equals(seniorId))
            .toList();
    }

    @TestConfiguration
    static class DeterministicEmbeddingConfig {

        @Bean
        @Primary
        EmbeddingClient deterministicEmbeddingClient() {
            return new EmbeddingClient() {
                @Override
                public float[] embedPassage(String text) {
                    return vectorize(text);
                }

                @Override
                public float[] embedQuery(String text) {
                    return vectorize(text);
                }

                @Override
                public String passageModelId() {
                    return "deterministic-korean-e2e-passage-v1";
                }

                @Override
                public int dimensions() {
                    return DIMENSIONS;
                }

                @Override
                public boolean isAvailable() {
                    return true;
                }
            };
        }

        /** 문자와 2-gram 해시를 정규화한 무료 결정적 벡터. 한국어 조사 변화도 일부 겹친다. */
        private static float[] vectorize(String raw) {
            String text = raw == null ? "" : raw.replaceAll("\\s+", "");
            float[] vector = new float[DIMENSIONS];
            for (int index = 0; index < text.length(); index++) {
                vector[Math.floorMod(text.charAt(index) * 31, DIMENSIONS)] += 1.0f;
                if (index + 1 < text.length()) {
                    int bigram = 31 * text.charAt(index) + text.charAt(index + 1);
                    vector[Math.floorMod(bigram, DIMENSIONS)] += 2.0f;
                }
            }
            double squared = 0.0;
            for (float value : vector) {
                squared += value * value;
            }
            if (squared == 0.0) {
                vector[0] = 1.0f;
                return vector;
            }
            float norm = (float) Math.sqrt(squared);
            for (int index = 0; index < vector.length; index++) {
                vector[index] /= norm;
            }
            return vector;
        }
    }
}
