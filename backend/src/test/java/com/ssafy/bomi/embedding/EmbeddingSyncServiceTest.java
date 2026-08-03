package com.ssafy.bomi.embedding;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.embedding.application.EmbeddingClient;
import com.ssafy.bomi.embedding.application.EmbeddingSyncService;
import com.ssafy.bomi.embedding.application.EmbeddingSyncService.SyncReport;
import com.ssafy.bomi.embedding.config.EmbeddingProperties;
import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryType;
import com.ssafy.bomi.memory.domain.MemoryVerificationStatus;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.vector.application.VectorCollection;
import com.ssafy.bomi.vector.application.VectorStore;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * The reindex job (S15P11E102-218). Real repositories, fake model, no cost.
 *
 * <p>Uses real JPA so the paging queries are exercised — {@code findNeedingEmbedding} is
 * where the spending cap is actually enforced, and a query that quietly ignores its
 * {@code Pageable} would pass any mock-based test while draining the API balance.</p>
 *
 * <p>The embedding client is a deterministic fake. Every assertion here is about
 * <em>bookkeeping</em> — which rows get picked, how many calls are made, what state a row is
 * left in — and none of that needs a real model. The real model is exercised exactly twice,
 * in the {@code billed} task.</p>
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class EmbeddingSyncServiceTest {

    private static final UUID SENIOR = UUID.randomUUID();
    private static final String MODEL = "embedding-passage";

    @Autowired MemoryRepository memoryRepository;
    @Autowired ConversationSummaryRepository summaryRepository;
    @Autowired PlatformTransactionManager transactionManager;
    @Autowired TestEntityManager em;

    private CountingEmbeddingClient embedding;
    private RecordingVectorStore store;
    private EmbeddingProperties properties;
    private EmbeddingSyncService service;

    @BeforeEach
    void setUp() {
        embedding = new CountingEmbeddingClient();
        store = new RecordingVectorStore();
        properties = new EmbeddingProperties();
        properties.setEnabled(true);
        properties.setApiKey("test-key");
        properties.setSyncBatchSize(3);
        service = new EmbeddingSyncService(memoryRepository, summaryRepository, embedding,
            store, properties, transactionManager);
    }

    // ── 1. 지출 상한 ─────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 한 번 실행이 batch 상한을 넘지 않는다 — 이것은 지출 상한이다")
    void oneRunNeverExceedsTheBatchCap() {
        /*
         * ★★ 한 행 = 과금 1회. 상한이 없으면 오래된 가구의 전체 재색인이 한 번의
         *    무제한 버스트가 된다. 잔액이 프로토타입 시연까지 감당해야 한다.
         */
        for (int i = 0; i < 10; i++) {
            persistMemory("기억 " + i, EmbeddingStatus.PENDING);
        }

        SyncReport report = service.syncDue();

        assertThat(report.billedCalls()).isEqualTo(3);
        assertThat(embedding.passageCalls).isEqualTo(3);
    }

    @Test
    @DisplayName("★ 기억과 요약이 각자 상한만큼 쓰지 않는다 — 합쳐서 상한이다")
    void memoriesAndSummariesShareOneCap() {
        /*
         * 두 종류가 각자 batchSize 만큼 쓰면 한 번에 두 배가 과금된다. 상한이
         * 상한이 아니게 되는데, 로그만 보면 "상한 3"이라 정상으로 보인다.
         */
        persistMemory("기억 1", EmbeddingStatus.PENDING);
        persistMemory("기억 2", EmbeddingStatus.PENDING);
        persistSummary("요약 1", EmbeddingStatus.PENDING);
        persistSummary("요약 2", EmbeddingStatus.PENDING);
        persistSummary("요약 3", EmbeddingStatus.PENDING);

        SyncReport report = service.syncDue();

        assertThat(report.billedCalls()).isEqualTo(3);
        assertThat(report.memoriesIndexed()).isEqualTo(2);
        assertThat(report.summariesIndexed()).isEqualTo(1);
    }

    // ── 2. 무엇을 집는가 ─────────────────────────────────────────────────────

    @Test
    void syncedRowsAreNotPaidForTwice() {
        persistMemory("이미 색인됨", EmbeddingStatus.SYNCED);
        persistMemory("아직", EmbeddingStatus.PENDING);

        service.syncDue();

        assertThat(embedding.passageCalls).isEqualTo(1);
        assertThat(embedding.embeddedTexts).containsExactly("아직");
    }

    @Test
    @DisplayName("★ FAILED 는 기본 실행에서 재시도하지 않는다")
    void failedRowsAreNotRetriedOnEveryTick() {
        /*
         * 실패는 대개 영구적이다(모델이 거부하는 내용). 매 틱마다 재시도하면 같은
         * 오류에 5분마다 돈을 낸다. 재시도는 사람이 결정하는 행위여야 한다.
         */
        persistMemory("계속 실패하는 것", EmbeddingStatus.FAILED);

        assertThat(service.syncDue().billedCalls()).isZero();
        assertThat(service.retryFailed().billedCalls()).isEqualTo(1);
    }

    @Test
    void rejectedAndSupersededMemoriesAreNotWorthPayingFor() {
        /*
         * findRetrievable 이 절대 돌려주지 않는 행이다. 색인해도 검색되지 않으므로
         * 호출값만 나간다. REJECTED 는 대개 잘못 들은 문장이라, 의미로 찾을 수
         * 있게 만들면 안 되는 쪽이기도 하다.
         */
        Memory rejected = Memory.create(SENIOR, MemoryType.OTHER, "잘못 들은 문장");
        rejected.changeVerificationStatus(MemoryVerificationStatus.REJECTED);
        memoryRepository.save(rejected);
        em.flush();

        assertThat(service.syncDue().billedCalls()).isZero();
    }

    // ── 3. 부기 ──────────────────────────────────────────────────────────────

    @Test
    void indexingRecordsWhichModelProducedTheVector() {
        Memory memory = persistMemory("무릎이 자주 아프시다", EmbeddingStatus.PENDING);

        service.syncDue();
        em.flush();
        em.clear();

        Memory reloaded = memoryRepository.findById(memory.getId()).orElseThrow();
        assertThat(reloaded.getEmbeddingStatus()).isEqualTo(EmbeddingStatus.SYNCED);
        assertThat(reloaded.getEmbeddingModel()).isEqualTo(MODEL);
        assertThat(reloaded.getEmbeddingSyncedAt()).isNotNull();
        assertThat(store.upserts).containsKey(memory.getId());
    }

    @Test
    void afailedRowIsMarkedRatherThanLeftLookingNew() {
        Memory memory = persistMemory("모델이 거부할 내용", EmbeddingStatus.PENDING);
        embedding.explodeOn = "모델이 거부할 내용";

        SyncReport report = service.syncDue();
        em.flush();
        em.clear();

        assertThat(report.failed()).isEqualTo(1);
        assertThat(memoryRepository.findById(memory.getId()).orElseThrow().getEmbeddingStatus())
            .isEqualTo(EmbeddingStatus.FAILED);
    }

    @Test
    @DisplayName("★ 한 행이 실패해도 이미 지불한 행의 부기는 남는다")
    void onefailureDoesNotRollBackRowsAlreadyPaidFor() {
        /*
         * ★★ 호출은 트랜잭션과 무관하게 이미 지불됐다. 한 행이 실패했다고 앞의
         *    성공 부기를 되돌리면, 다음 실행이 같은 행을 다시 사게 된다.
         *
         * 이 테스트가 증명하는 것과 못 하는 것을 구분해 둔다. @DataJpaTest 는 테스트
         * 전체를 한 트랜잭션으로 감싸므로, 여기서 도는 TransactionTemplate 은 그
         * 바깥 트랜잭션에 합류한다. 따라서 이것은 '행별 커밋 경계'를 증명하지 않는다.
         * 증명하는 것은 하나다 — 뒤 행의 예외가 앞 행의 부기를 지우지 않는다.
         * 그것만으로도 회귀를 잡는다: 예외를 위로 던지도록 바꾸면 이 테스트가 깨진다.
         */
        Memory first = persistMemory("첫 번째", EmbeddingStatus.PENDING);
        persistMemory("두 번째", EmbeddingStatus.PENDING);
        embedding.explodeOn = "두 번째";

        service.syncDue();
        em.flush();
        em.clear();

        assertThat(memoryRepository.findById(first.getId()).orElseThrow().getEmbeddingStatus())
            .isEqualTo(EmbeddingStatus.SYNCED);
    }

    // ── 4. 스토어가 없을 때 ──────────────────────────────────────────────────

    @Test
    @DisplayName("★ 스토어가 죽었을 때 행을 FAILED 로 만들지 않는다")
    void anunreachableStoreDoesNotBurnTheRetryBudgetOfHealthyRows() {
        /*
         * '스토어가 죽었다'와 '이 행은 임베딩할 수 없다'는 다른 사실이다. 섞으면
         * 멀쩡한 행들이 전부 FAILED 가 되고, FAILED 는 기본 실행에서 재시도하지
         * 않으므로 스토어가 돌아와도 아무것도 복구되지 않는다.
         */
        Memory memory = persistMemory("기억", EmbeddingStatus.PENDING);
        store.available = false;

        SyncReport report = service.syncDue();
        em.flush();
        em.clear();

        assertThat(report.skipped()).isTrue();
        assertThat(embedding.passageCalls).isZero();
        assertThat(memoryRepository.findById(memory.getId()).orElseThrow().getEmbeddingStatus())
            .isEqualTo(EmbeddingStatus.PENDING);
    }

    // ── 5. 모델 교체 ─────────────────────────────────────────────────────────

    @Test
    @DisplayName("★ 모델이 바뀌면 기존 벡터는 전부 STALE 이다 — 다른 벡터 공간이다")
    void amodelChangeInvalidatesEveryExistingVector() {
        /*
         * 다른 모델의 벡터는 단지 나쁜 것이 아니라 '의미가 없다'. 벡터 공간이
         * 다르면 유사도 숫자는 평범해 보이지만 아무것도 뜻하지 않는다. 이 표시는
         * 과금되지 않는다 — UPDATE 두 번이고, 재임베딩은 상한 안에서 나중에 일어난다.
         */
        Memory old = persistMemory("옛 모델로 색인됨", EmbeddingStatus.PENDING);
        old.markEmbeddingSynced("some-older-model", OffsetDateTime.now());
        memoryRepository.save(old);
        Memory current = persistMemory("현재 모델", EmbeddingStatus.PENDING);
        current.markEmbeddingSynced(MODEL, OffsetDateTime.now());
        memoryRepository.save(current);
        em.flush();

        service.markStaleAfterModelChange();
        em.flush();
        em.clear();

        assertThat(memoryRepository.findById(old.getId()).orElseThrow().getEmbeddingStatus())
            .isEqualTo(EmbeddingStatus.STALE);
        assertThat(memoryRepository.findById(current.getId()).orElseThrow().getEmbeddingStatus())
            .as("같은 모델로 색인된 행은 건드리지 않는다 — 건드리면 전량 재과금이다")
            .isEqualTo(EmbeddingStatus.SYNCED);
        assertThat(embedding.passageCalls).isZero();
    }

    @Test
    @DisplayName("★ Qdrant 를 통째로 잃어도 부기 컬럼으로 복구된다")
    void wipingTheVectorStoreIsRecoverableFromTheBookkeepingColumns() {
        /*
         * ★★ 이것이 "Postgres 가 권위, Qdrant 는 파생 인덱스"라는 말의 실제 의미다.
         *    볼륨을 백업하지 않는 근거이기도 하다(오히려 백업하면 낡은 payload 가
         *    되살아나 공개범위가 바뀐 기억을 노출할 수 있다).
         */
        Memory memory = persistMemory("복구되어야 할 기억", EmbeddingStatus.PENDING);
        service.syncDue();
        em.flush();
        assertThat(store.upserts).containsKey(memory.getId());

        // 스토어가 통째로 사라졌다.
        store.upserts.clear();
        // 운영자가 재색인을 지시한다: 부기를 되돌리고 다시 돌린다.
        Memory reloaded = memoryRepository.findById(memory.getId()).orElseThrow();
        reloaded.markEmbeddingStale();
        memoryRepository.save(reloaded);
        em.flush();

        SyncReport report = service.syncDue();

        assertThat(report.memoriesIndexed()).isEqualTo(1);
        assertThat(store.upserts).containsKey(memory.getId());
    }

    // ── 도우미 ───────────────────────────────────────────────────────────────

    private Memory persistMemory(String content, EmbeddingStatus status) {
        Memory memory = Memory.create(SENIOR, MemoryType.OTHER, content);
        if (status == EmbeddingStatus.SYNCED) {
            memory.markEmbeddingSynced(MODEL, OffsetDateTime.now());
        } else if (status == EmbeddingStatus.FAILED) {
            memory.markEmbeddingFailed();
        } else if (status == EmbeddingStatus.STALE) {
            memory.markEmbeddingStale();
        }
        Memory saved = memoryRepository.save(memory);
        em.flush();
        return saved;
    }

    /**
     * Counter that keeps each summary's period distinct.
     *
     * <p>{@code conversation_summary} is unique on
     * {@code (senior_id, summary_type, period_started_at, period_ended_at)}. Using
     * {@code now()} for every summary made three of them collide, and the test passed only
     * because consecutive {@code now()} calls usually differ by a fraction of a microsecond.
     * It failed the moment two landed on the same value — a flake that looks like a bug in
     * the sync job rather than in the fixture.</p>
     */
    private int summaryCount = 0;

    private ConversationSummary persistSummary(String content, EmbeddingStatus status) {
        // 요약마다 다른 기간을 준다. 같은 기간을 쓰면 유일 제약에 걸린다.
        OffsetDateTime periodEnd = OffsetDateTime.now().minusDays(++summaryCount);
        ConversationSummary summary = ConversationSummary.forConversation(
            SENIOR, UUID.randomUUID(),
            periodEnd.minusHours(1), periodEnd, content, 3);
        if (status == EmbeddingStatus.SYNCED) {
            summary.markEmbeddingSynced(MODEL, OffsetDateTime.now());
        }
        ConversationSummary saved = summaryRepository.save(summary);
        em.flush();
        return saved;
    }

    // ── 대역 ─────────────────────────────────────────────────────────────────

    /** Counts calls so a test can assert the spending cap, and never touches the network. */
    private static class CountingEmbeddingClient implements EmbeddingClient {
        int passageCalls = 0;
        final List<String> embeddedTexts = new ArrayList<>();
        String explodeOn = null;

        @Override
        public float[] embedPassage(String text) {
            passageCalls++;
            embeddedTexts.add(text);
            if (text.equals(explodeOn)) {
                throw new EmbeddingFailedException("model refused this input");
            }
            return new float[] {1.0f, 0.0f};
        }

        @Override
        public float[] embedQuery(String text) {
            throw new AssertionError("the sync job must never use the query model");
        }

        @Override
        public String passageModelId() {
            return MODEL;
        }

        @Override
        public int dimensions() {
            return 2;
        }

        @Override
        public boolean isAvailable() {
            return true;
        }
    }

    private static class RecordingVectorStore implements VectorStore {
        final Map<UUID, float[]> upserts = new LinkedHashMap<>();
        boolean available = true;

        @Override
        public void ensureCollections() {
        }

        @Override
        public void upsert(VectorCollection collection, UUID id, UUID seniorId, float[] vector) {
            upserts.put(id, vector);
        }

        @Override
        public List<VectorHit> search(VectorCollection collection, UUID seniorId,
            float[] queryVector, int limit) {
            return List.of();
        }

        @Override
        public void delete(VectorCollection collection, UUID id) {
            upserts.remove(id);
        }

        @Override
        public boolean isAvailable() {
            return available;
        }
    }
}
