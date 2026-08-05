package com.ssafy.bomi.context;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.context.api.ConversationContextRequest;
import com.ssafy.bomi.context.api.ConversationContextResponse;
import com.ssafy.bomi.context.application.ConversationContextService;
import com.ssafy.bomi.context.application.MemorySemanticSearch;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import com.ssafy.bomi.memory.domain.MemoryType;
import com.ssafy.bomi.memory.domain.MemoryVerificationStatus;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.relationship.domain.CareRelationship;
import com.ssafy.bomi.relationship.domain.RelationshipPriority;
import com.ssafy.bomi.relationship.repository.CareRelationshipRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.mockito.ArgumentMatchers;
import org.mockito.Mockito;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Transactional;

/**
 * The privacy boundary between the vector store and the answer (S15P11E102-218).
 *
 * <p><b>This is the test the ticket calls the authority re-verification.</b> The vector store
 * is a derived index and its payload can be out of date by an arbitrary amount — a memory
 * indexed while it was {@code SHARED} keeps that payload after the senior changes their mind.
 * If a hit from the store could add a row to the answer, that stale copy would leak
 * something the senior has since withdrawn.</p>
 *
 * <p>The design that prevents it is not a check somewhere; it is the <em>order</em>.
 * {@code ConversationContextService} loads the retrievable set from PostgreSQL first and
 * uses similarity only to rank what it already has. A hit for a memory that is not in that
 * set has nowhere to go. These tests pin that order by feeding in hits that are deliberately
 * wrong and asserting they change nothing.</p>
 *
 * <p>Its own class rather than a case in {@code ConversationContextServiceTest} because that
 * class pins the <em>fallback</em> behaviour — semantic search reported unavailable — and a
 * stub search bean would change what it is testing.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false"
    })
@Transactional
class SemanticHitsDoNotBypassTheAuthorityFilterTest {

    private static EmbeddedPostgres postgres;

    @Autowired private ConversationContextService contextService;
    @Autowired private AppUserRepository appUserRepository;
    @Autowired private MemoryRepository memoryRepository;
    @Autowired private ConversationSummaryRepository summaryRepository;
    @Autowired private CareRelationshipRepository careRelationshipRepository;
    /**
     * Replaces the real search bean rather than competing with it.
     *
     * <p>A second {@code @Primary} implementation does not win — it fails startup with "more
     * than one 'primary' bean found", because {@code QdrantMemorySearch} is already
     * {@code @Primary} over the no-op stand-in. {@code @MockitoBean} replaces the definition
     * instead of adding one, which is what a test that wants to control this collaborator
     * actually means.</p>
     */
    @MockitoBean private MemorySemanticSearch semanticSearch;

    private AppUser senior;
    private AppUser guardian;

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
    void setUp() {
        senior = appUserRepository.save(AppUser.create("SENIOR", "김순자", null, "순자님"));
        guardian = appUserRepository.save(AppUser.create("GUARDIAN", "김영수", null, "영수님"));
        careRelationshipRepository.save(CareRelationship.create(
            senior.getId(), guardian.getId(), RelationshipPriority.PRIMARY));
        Mockito.when(semanticSearch.isAvailable()).thenReturn(true);
        givenHits();
    }

    /** Feeds the assembly exactly these hits, however wrong they are. */
    private void givenHits(MemorySemanticSearch.SemanticHit... hits) {
        Mockito.when(semanticSearch.search(
                ArgumentMatchers.any(), ArgumentMatchers.any(), ArgumentMatchers.anyInt(),
                ArgumentMatchers.anyInt()))
            .thenReturn(new MemorySemanticSearch.SearchResult(
                List.of(hits), List.of(), true, null, 1));
    }

    private void givenSummaryHits(MemorySemanticSearch.SemanticHit... hits) {
        Mockito.when(semanticSearch.search(
                ArgumentMatchers.any(), ArgumentMatchers.any(), ArgumentMatchers.anyInt(),
                ArgumentMatchers.anyInt()))
            .thenReturn(new MemorySemanticSearch.SearchResult(
                List.of(), List.of(hits), true, null, 1));
    }

    // ── 낡은 payload 는 답을 만들지 못한다 ───────────────────────────────────

    @Test
    @DisplayName("★★ 색인 후 PRIVATE 으로 바뀐 기억은 보호자에게 새지 않는다")
    void amemoryHiddenAfterIndexingDoesNotLeakToTheGuardian() {
        /*
         * ★★★ 이 티켓에서 가장 중요한 테스트다.
         *
         * 시나리오: 어르신이 어떤 이야기를 공유 가능(SHARED)으로 두었고 그때 색인됐다.
         * 나중에 마음을 바꿔 PRIVATE 으로 돌렸다. Qdrant 의 payload 는 그대로다.
         *
         * 벡터 스토어의 hit 가 답에 행을 '추가'할 수 있다면, 어르신이 거두어들인
         * 이야기가 보호자 화면에 뜬다. 재검증은 성능 낭비가 아니라 방어 계층이다.
         */
        Memory withdrawn = Memory.create(
            senior.getId(), MemoryType.OTHER, "며느리와 사이가 불편하다");
        withdrawn.changeVisibility(MemoryVisibility.PRIVATE);
        memoryRepository.save(withdrawn);

        // 낡은 색인이 이 기억을 아주 높은 점수로 돌려준다.
        givenHits(new MemorySemanticSearch.SemanticHit(withdrawn.getId(), 0.99));

        ConversationContextResponse asGuardian = contextService.assemble(
            senior.getId(),
            new ConversationContextRequest("며느리", null, null, null, false, guardian.getId()));

        assertThat(asGuardian.memories())
            .extracting(ConversationContextResponse.MemoryItem::content)
            .doesNotContain("며느리와 사이가 불편하다");
    }

    @Test
    @DisplayName("★ 대체된(SUPERSEDED) 기억은 hit 가 있어도 되살아나지 않는다")
    void asupersededMemoryCannotBeResurrectedByAStaleHit() {
        /*
         * 대체된 사실은 '바뀐 사실'이다. 되살리면 로봇이 더 이상 참이 아닌 것을
         * 현재형으로 말한다 — 복약처럼 사실이 바뀌는 영역에서 특히 위험하다.
         */
        Memory old = Memory.create(senior.getId(), MemoryType.OTHER, "혈압약을 아침에 드신다");
        old.changeVisibility(MemoryVisibility.SHARED_WITH_GUARDIANS);
        old.changeLifecycleStatus(MemoryLifecycleStatus.SUPERSEDED);
        memoryRepository.save(old);

        givenHits(new MemorySemanticSearch.SemanticHit(old.getId(), 0.99));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(),
            new ConversationContextRequest("혈압약", null, null, null, false, null));

        assertThat(context.memories())
            .extracting(ConversationContextResponse.MemoryItem::content)
            .doesNotContain("혈압약을 아침에 드신다");
    }

    @Test
    @DisplayName("★ 거부된(REJECTED) 추출은 hit 가 있어도 프롬프트에 닿지 않는다")
    void arejectedExtractionNeverReachesThePrompt() {
        /*
         * 거부된 추출은 대개 ASR 이 잘못 들은 문장이다. 의미로 찾을 수 있게 만들면
         * 안 되는 쪽이고, 그래서 색인 대상에서도 빠진다(findNeedingEmbedding).
         * 그럼에도 옛 벡터가 남아 있을 수 있으므로 읽는 쪽에서도 막는다.
         */
        Memory rejected = Memory.create(senior.getId(), MemoryType.OTHER, "칼을 샀다");
        rejected.changeVisibility(MemoryVisibility.SHARED_WITH_GUARDIANS);
        rejected.changeVerificationStatus(MemoryVerificationStatus.REJECTED);
        memoryRepository.save(rejected);

        givenHits(new MemorySemanticSearch.SemanticHit(rejected.getId(), 0.99));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("칼", null, null, null, false, null));

        assertThat(context.memories())
            .extracting(ConversationContextResponse.MemoryItem::content)
            .doesNotContain("칼을 샀다");
    }

    @Test
    @DisplayName("★ 다른 어르신의 id 를 돌려줘도 행이 추가되지 않는다")
    void ahitForSomebodyElsesMemoryAddsNothing() {
        /*
         * seniorId 필터는 Qdrant payload 에도 있지만, 그것은 효율을 위한 것이지
         * 경계가 아니다. payload 가 틀렸거나 컬렉션이 오염돼도 답은 바뀌지 않아야 한다.
         */
        AppUser other = appUserRepository.save(AppUser.create("SENIOR", "이철수", null, "철수님"));
        Memory theirs = Memory.create(other.getId(), MemoryType.OTHER, "낚시를 좋아하신다");
        theirs.changeVisibility(MemoryVisibility.SHARED_WITH_GUARDIANS);
        memoryRepository.save(theirs);

        givenHits(new MemorySemanticSearch.SemanticHit(theirs.getId(), 0.99));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("낚시", null, null, null, false, null));

        assertThat(context.memories()).isEmpty();
    }

    @Test
    @DisplayName("★ 존재하지 않는 id 를 돌려줘도 터지지 않는다")
    void ahitForADeletedRowIsSimplyIgnored() {
        /*
         * 행이 지워졌는데 벡터가 남아 있는 상태다. 스토어가 파생 인덱스인 이상
         * 항상 가능한 상태이고, 여기서 예외가 나면 색인 정리 지연이 곧 턴 실패가 된다.
         */
        givenHits(new MemorySemanticSearch.SemanticHit(UUID.randomUUID(), 0.99));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무엇이든", null, null, null, false, null));

        assertThat(context.memories()).isEmpty();
    }

    // ── 유사도는 '순서'를 바꾼다. 그것이 하는 일의 전부다 ────────────────────

    @Test
    @DisplayName("허용된 기억들 사이에서는 유사도가 순위를 바꾼다")
    void similarityReordersTheMemoriesThatAreAllowedThrough() {
        /*
         * 재검증이 hit 를 전부 무시한다는 뜻이 아니다. 허용된 집합 안에서는
         * 유사도가 실제로 순위를 정한다 — 그러지 않으면 이 티켓 전체가 의미가 없다.
         */
        Memory knee = allowed("무릎이 아프다고 자주 말씀하신다");
        Memory fishing = allowed("낚시를 좋아하신다");

        givenHits(new MemorySemanticSearch.SemanticHit(fishing.getId(), 0.95),
            new MemorySemanticSearch.SemanticHit(knee.getId(), 0.10));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, null, null, false, null));

        assertThat(context.memories())
            .extracting(ConversationContextResponse.MemoryItem::content)
            .first()
            .as("의미 점수가 높은 쪽이 앞에 온다. 키워드만 보면 '무릎'이 앞이어야 한다")
            .isEqualTo("낚시를 좋아하신다");
    }

    @Test
    @DisplayName("의역 질의도 의미 hit 가 PostgreSQL 허용 기억 안에서 순위를 바꾼다")
    void paraphraseUsesSemanticRankingWithinTheAllowedSet() {
        Memory walking = allowed("저녁 산책이 가장 즐겁다고 하셨다");
        Memory television = allowed("저녁에는 뉴스를 보신다");
        givenHits(new MemorySemanticSearch.SemanticHit(walking.getId(), 0.92),
            new MemorySemanticSearch.SemanticHit(television.getId(), 0.15));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest(
                "밖에 나가서 좀 걷고 싶어", null, null, null, false, null));

        assertThat(context.memories())
            .extracting(ConversationContextResponse.MemoryItem::id)
            .startsWith(walking.getId());
    }

    @Test
    @DisplayName("★ 다른 어르신의 요약 hit 는 PostgreSQL 후보에 추가되지 않는다")
    void ahitForSomebodyElsesSummaryAddsNothing() {
        ConversationSummary mine = saveSummary(senior.getId(), "무릎 이야기를 나눴다", 1);
        AppUser other = appUserRepository.save(AppUser.create("SENIOR", "이철수", null, "철수님"));
        ConversationSummary theirs = saveSummary(other.getId(), "낚시 이야기를 나눴다", 2);
        givenSummaryHits(new MemorySemanticSearch.SemanticHit(theirs.getId(), 0.99));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("낚시", null, null, null, false, null));

        assertThat(context.relevantSummaries())
            .extracting(ConversationContextResponse.SummaryItem::id)
            .containsExactly(mine.getId())
            .doesNotContain(theirs.getId());
        assertThat(context.retrieval().hitCount())
            .as("권위 필터를 통과하지 못한 벡터 hit 는 실제 hit 수에 포함하지 않는다")
            .isZero();
    }

    @Test
    @DisplayName("허용된 요약들 사이에서는 의미 유사도가 순위를 바꾼다")
    void similarityReordersOnlyTheAllowedSummaries() {
        ConversationSummary knee = saveSummary(senior.getId(), "무릎 이야기를 나눴다", 1);
        ConversationSummary fishing = saveSummary(senior.getId(), "낚시 이야기를 나눴다", 2);
        givenSummaryHits(new MemorySemanticSearch.SemanticHit(fishing.getId(), 0.95),
            new MemorySemanticSearch.SemanticHit(knee.getId(), 0.10));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, null, null, false, null));

        assertThat(context.relevantSummaries())
            .extracting(ConversationContextResponse.SummaryItem::id)
            .startsWith(fishing.getId());
        assertThat(context.retrieval().semanticUsed()).isTrue();
        assertThat(context.retrieval().hitCount()).isEqualTo(2);
    }

    private Memory allowed(String content) {
        Memory memory = Memory.create(senior.getId(), MemoryType.OTHER, content);
        memory.changeVisibility(MemoryVisibility.SHARED_WITH_GUARDIANS);
        memory.setImportance((short) 3);
        return memoryRepository.save(memory);
    }

    private ConversationSummary saveSummary(UUID owner, String content, int daysAgo) {
        OffsetDateTime end = OffsetDateTime.now().minusDays(daysAgo);
        return summaryRepository.save(ConversationSummary.forDay(
            owner, end.minusHours(1), end, content, 2));
    }
}
