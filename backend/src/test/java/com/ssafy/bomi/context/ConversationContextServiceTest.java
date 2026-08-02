package com.ssafy.bomi.context;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.ssafy.bomi.activity.domain.DailyActivityMetric;
import com.ssafy.bomi.activity.repository.DailyActivityMetricRepository;
import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.context.api.ConversationContextRequest;
import com.ssafy.bomi.context.api.ConversationContextResponse;
import com.ssafy.bomi.context.application.ConversationContextService;
import com.ssafy.bomi.conversation.domain.Conversation;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.domain.MessagePriority;
import com.ssafy.bomi.conversation.domain.MessageRole;
import com.ssafy.bomi.conversation.domain.MessageTriggerType;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationRepository;
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
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import io.zonky.test.db.postgres.embedded.EmbeddedPostgres;
import java.io.IOException;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Transactional;

/**
 * Verifies the completion conditions of S15P11E102-203 against a real PostgreSQL.
 *
 * <p>Runs on real PostgreSQL rather than H2 because the schema this reads was built by
 * Flyway, and H2 does not reproduce the array and JSONB behaviour the profile,
 * keywords, and care-record details depend on.</p>
 *
 * <p>Semantic search is deliberately left unwired here, which is the state the system
 * is actually in until S15P11E102-218. So these tests also pin the fallback behaviour:
 * retrieval must still return sensible memories, and it must say out loud that
 * similarity ranking was unavailable.</p>
 */
@SpringBootTest(
    properties = {
        "spring.flyway.enabled=true",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.jpa.open-in-view=false",
        "bomi.mqtt.enabled=false"
    })
@Transactional
class ConversationContextServiceTest {

    private static EmbeddedPostgres postgres;

    @Autowired private ConversationContextService contextService;
    @Autowired private AppUserRepository appUserRepository;
    @Autowired private CareRelationshipRepository careRelationshipRepository;
    @Autowired private ConversationRepository conversationRepository;
    @Autowired private ConversationMessageRepository messageRepository;
    @Autowired private ConversationSummaryRepository summaryRepository;
    @Autowired private MemoryRepository memoryRepository;
    @Autowired private CareRecordRepository careRecordRepository;
    @Autowired private DailyActivityMetricRepository metricRepository;

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
        senior.changeHealthDataConsent(ConsentStatus.GRANTED);
        senior.changeScheduleConsent(ConsentStatus.GRANTED);
        senior.updateConversationPreferences(Map.of(
            "avoid_topics", List.of("남편 사망"),
            "tone", "warm"));
        appUserRepository.save(senior);
    }

    // ── 완료 조건 1: 단일 호출로 6종 조립 ────────────────────────────────────

    @Test
    void singleCallAssemblesAllSixKinds() {
        Conversation conversation = conversationRepository.save(Conversation.open(senior.getId()));
        messageRepository.save(ConversationMessage.reactive(
            conversation.getId(), 1, MessageRole.SENIOR, "무릎이 아파", OffsetDateTime.now()));
        summaryRepository.save(ConversationSummary.forConversation(
            senior.getId(), conversation.getId(),
            OffsetDateTime.now().minusHours(1), OffsetDateTime.now(), "무릎 통증 대화", 2));
        summaryRepository.save(ConversationSummary.forDay(
            senior.getId(), OffsetDateTime.now().minusDays(1), OffsetDateTime.now().minusDays(1),
            "어제 무릎이 아프다고 하셨다", 5));
        saveMemory("작년부터 무릎이 아프시다", List.of("무릎"), (short) 5);
        careRecordRepository.save(CareRecord.create(
            senior.getId(), "MEDICATION", Map.of("name", "혈압약", "dose", "1정")));
        metricRepository.save(openTodayMetric());

        ConversationContextResponse context = contextService.assemble(
            senior.getId(),
            new ConversationContextRequest("무릎이 아파", conversation.getId(), 6, 8, false, null));

        // 1. 프로필·선호
        assertThat(context.profile().preferredName()).isEqualTo("순자님");
        assertThat(context.profile().quietHoursStart()).isEqualTo("22:00");
        // 회피 주제는 '정보'가 아니라 금지문으로 쓰이므로 반드시 실려야 한다.
        assertThat(context.profile().avoidTopics()).containsExactly("남편 사망");
        // 2. 오늘 상태
        assertThat(context.todayState()).isNotNull();
        assertThat(context.todayState().mealCount()).isEqualTo((short) 2);
        // 3. 최근 Raw
        assertThat(context.recentMessages()).hasSize(1);
        assertThat(context.recentMessages().get(0).content()).isEqualTo("무릎이 아파");
        // 4. 요약 (현재 대화 요약 + 관련 요약)
        assertThat(context.conversationSummary()).isEqualTo("무릎 통증 대화");
        assertThat(context.relevantSummaries()).hasSize(1);
        // 5. 장기 기억
        assertThat(context.memories()).hasSize(1);
        assertThat(context.memories().get(0).content()).contains("무릎");
        // 6. 동의된 돌봄 기록
        assertThat(context.careRecords()).hasSize(1);
        assertThat(context.careRecords().get(0).recordType()).isEqualTo("MEDICATION");
    }

    /**
     * The current conversation's summary must not also appear in the relevant list.
     *
     * <p>It is returned in its own field; duplicating it spends prompt budget on the
     * robot repeating itself.
     */
    @Test
    void currentConversationSummaryIsNotDuplicatedInRelevantSummaries() {
        Conversation conversation = conversationRepository.save(Conversation.open(senior.getId()));
        summaryRepository.save(ConversationSummary.forConversation(
            senior.getId(), conversation.getId(),
            OffsetDateTime.now().minusHours(1), OffsetDateTime.now(), "지금 대화 요약", 2));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(),
            new ConversationContextRequest("", conversation.getId(), null, null, false, null));

        assertThat(context.conversationSummary()).isEqualTo("지금 대화 요약");
        assertThat(context.relevantSummaries()).isEmpty();
    }

    // ── 완료 조건 2: top-k 3~10 조절 ─────────────────────────────────────────

    @Test
    void memoryTopKIsHonouredWithinRange() {
        for (int index = 0; index < 12; index++) {
            saveMemory("기억 " + index, List.of("무릎"), (short) 3);
        }

        assertThat(assembleWithTopK(3).memories()).hasSize(3);
        assertThat(assembleWithTopK(10).memories()).hasSize(10);
    }

    /**
     * Out-of-range top-k is clamped, not rejected.
     *
     * <p>The robot lowers its own top-k under network or resource pressure — the first
     * step of its degradation order. A 400 there would turn a graceful degradation into
     * a failed turn.
     */
    @Test
    void outOfRangeTopKIsClampedRatherThanRejected() {
        for (int index = 0; index < 12; index++) {
            saveMemory("기억 " + index, List.of("무릎"), (short) 3);
        }

        assertThat(assembleWithTopK(1).memories()).hasSize(3);
        assertThat(assembleWithTopK(99).memories()).hasSize(10);
    }

    // ── 완료 조건 3: 문맥 과적재 방지 ────────────────────────────────────────

    @Test
    void neitherAllSummariesNorAllMemoriesAreAttached() {
        for (int index = 0; index < 20; index++) {
            saveMemory("기억 " + index, List.of("무릎"), (short) 3);
            summaryRepository.save(ConversationSummary.forDay(
                senior.getId(),
                OffsetDateTime.now().minusDays(index + 1L),
                OffsetDateTime.now().minusDays(index + 1L),
                "요약 " + index, 3));
        }

        ConversationContextResponse context = contextService.assemble(
            senior.getId(),
            new ConversationContextRequest("무릎", null, null, null, false, null));

        assertThat(context.memories()).hasSizeLessThanOrEqualTo(10);
        assertThat(context.relevantSummaries()).hasSizeLessThanOrEqualTo(3);
    }

    @Test
    void recentMessageWindowIsCappedAtTwelve() {
        Conversation conversation = conversationRepository.save(Conversation.open(senior.getId()));
        for (int index = 1; index <= 20; index++) {
            messageRepository.save(ConversationMessage.reactive(
                conversation.getId(), index, MessageRole.SENIOR, "말 " + index,
                OffsetDateTime.now().minusMinutes(20L - index)));
        }

        ConversationContextResponse context = contextService.assemble(
            senior.getId(),
            new ConversationContextRequest("", conversation.getId(), null, 99, false, null));

        assertThat(context.recentMessages()).hasSize(12);
        // 시간순이어야 한다. 프롬프트가 역순으로 읽으면 대화가 뒤집힌다.
        assertThat(context.recentMessages().get(0).content()).isEqualTo("말 9");
        assertThat(context.recentMessages().get(11).content()).isEqualTo("말 20");
    }

    // ── 선필터: 프라이버시·정확성 규칙 ───────────────────────────────────────

    @Test
    void rejectedAndSupersededMemoriesNeverSurface() {
        Memory rejected = Memory.create(senior.getId(), MemoryType.OTHER, "잘못 들은 내용");
        rejected.changeVerificationStatus(MemoryVerificationStatus.REJECTED);
        memoryRepository.save(rejected);

        Memory superseded = Memory.create(senior.getId(), MemoryType.OTHER, "바뀐 옛 사실");
        superseded.changeLifecycleStatus(MemoryLifecycleStatus.SUPERSEDED);
        memoryRepository.save(superseded);

        Memory usable = saveMemory("현재 사실", List.of("사실"), (short) 3);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, 10, null, false, null));

        assertThat(context.memories()).extracting(ConversationContextResponse.MemoryItem::id)
            .containsExactly(usable.getId());
    }

    @Test
    void anotherSeniorsMemoriesAreNeverReturned() {
        AppUser other = appUserRepository.save(AppUser.create("SENIOR", "다른 어르신"));
        memoryRepository.save(Memory.create(other.getId(), MemoryType.OTHER, "남의 기억"));
        saveMemory("내 기억", List.of("기억"), (short) 3);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, 10, null, false, null));

        assertThat(context.memories()).hasSize(1);
        assertThat(context.memories().get(0).content()).isEqualTo("내 기억");
    }

    /**
     * The robot talking to the senior may use PRIVATE memories; a guardian may not.
     *
     * <p>This is what makes T4 ("just between us") real. If a guardian could read
     * PRIVATE, the senior would stop confiding and the emotional pillar dies.
     */
    @Test
    void privateMemoriesAreRobotOnlyAndHiddenFromGuardians() {
        Memory privateMemory = saveMemory("아무에게도 말하지 마세요", List.of("비밀"), (short) 4);
        Memory sharedMemory = Memory.create(
            senior.getId(), MemoryType.OTHER, "보호자와 공유해도 되는 내용",
            MemoryVisibility.SHARED_WITH_GUARDIANS);
        memoryRepository.save(sharedMemory);

        UUID guardianId = appUserRepository.save(AppUser.create("GUARDIAN", "아들")).getId();
        careRelationshipRepository.save(CareRelationship.create(
            senior.getId(), guardianId, RelationshipPriority.SECONDARY));

        List<UUID> robotView = contextService.assemble(
                senior.getId(), new ConversationContextRequest("", null, 10, null, false, null))
            .memories().stream().map(ConversationContextResponse.MemoryItem::id).toList();
        List<UUID> guardianView = contextService.assemble(
                senior.getId(),
                new ConversationContextRequest("", null, 10, null, false, guardianId))
            .memories().stream().map(ConversationContextResponse.MemoryItem::id).toList();

        assertThat(robotView).contains(privateMemory.getId(), sharedMemory.getId());
        assertThat(guardianView).containsExactly(sharedMemory.getId());
    }

    /**
     * A guardian with no active relationship is refused, not quietly given nothing.
     *
     * <p>An empty result would read as "nothing was shared", which hides a permission
     * bug instead of surfacing it.
     */
    @Test
    void guardianWithoutActiveRelationshipIsRefused() {
        UUID stranger = appUserRepository.save(AppUser.create("GUARDIAN", "남")).getId();

        assertThatThrownBy(() -> contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, stranger)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("no active care relationship");
    }

    // ── 동의 게이트 ──────────────────────────────────────────────────────────

    @Test
    void careRecordsRequirePerCategoryConsent() {
        careRecordRepository.save(CareRecord.create(
            senior.getId(), "MEDICATION", Map.of("name", "혈압약")));
        careRecordRepository.save(CareRecord.create(
            senior.getId(), "APPOINTMENT", Map.of("where", "정형외과")));

        senior.changeHealthDataConsent(ConsentStatus.DENIED);
        appUserRepository.save(senior);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        // 일정 동의는 남아 있으므로 APPOINTMENT 만 보인다.
        assertThat(context.careRecords()).extracting(
            ConversationContextResponse.CareRecordItem::recordType).containsExactly("APPOINTMENT");
    }

    // ── 가용성 보고: 비어 있는 것과 불가능한 것은 다르다 ─────────────────────

    @Test
    void unavailableSemanticSearchIsReportedRatherThanHidden() {
        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, null, null, false, null));

        assertThat(context.availability().semanticSearch()).isFalse();
        assertThat(context.availability().notes())
            .anySatisfy(note -> assertThat(note).contains("semantic search unavailable"));
    }

    @Test
    void documentsAreEmptyUnlessRequestedAndUnavailabilityIsReported() {
        ConversationContextResponse withoutFlag = contextService.assemble(
            senior.getId(), new ConversationContextRequest("복지", null, null, null, false, null));
        ConversationContextResponse withFlag = contextService.assemble(
            senior.getId(), new ConversationContextRequest("복지", null, null, null, true, null));

        assertThat(withoutFlag.documents()).isEmpty();
        assertThat(withoutFlag.availability().notes())
            .noneSatisfy(note -> assertThat(note).contains("document corpus"));

        assertThat(withFlag.documents()).isEmpty();
        assertThat(withFlag.availability().documentCorpus()).isFalse();
        assertThat(withFlag.availability().notes())
            .anySatisfy(note -> assertThat(note).contains("document corpus"));
    }

    // ── 재정렬: 중요도와 최근성이 실제로 작동하는가 ──────────────────────────

    @Test
    void higherImportanceWinsWhenRelevanceAndRecencyMatch() {
        Memory trivial = saveMemory("사소한 내용", List.of("무릎"), (short) 1);
        Memory important = saveMemory("중요한 내용", List.of("무릎"), (short) 5);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, 3, null, false, null));

        assertThat(context.memories().get(0).id()).isEqualTo(important.getId());
        assertThat(context.memories().get(0).score())
            .isGreaterThan(context.memories().get(1).score());
        assertThat(context.memories()).extracting(ConversationContextResponse.MemoryItem::id)
            .contains(trivial.getId());
    }

    @Test
    void keywordMatchOutranksUnrelatedMemoryOfEqualImportance() {
        Memory unrelated = saveMemory("손자가 왔다", List.of("손자"), (short) 3);
        Memory related = saveMemory("무릎이 아프다", List.of("무릎"), (short) 3);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, 3, null, false, null));

        assertThat(context.memories().get(0).id()).isEqualTo(related.getId());
        // 관련 없는 기억도 완전히 배제되지는 않는다. 0 점으로 떨구면 검색이 조용히
        // '아무것도 기억하지 못하는' 상태가 된다.
        assertThat(context.memories()).extracting(ConversationContextResponse.MemoryItem::id)
            .contains(unrelated.getId());
    }

    // ── 진행 중 대화가 없는 첫 턴 ────────────────────────────────────────────

    @Test
    void firstTurnWithoutConversationStillAssembles() {
        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("안녕", null, null, null, false, null));

        assertThat(context.profile()).isNotNull();
        assertThat(context.recentMessages()).isEmpty();
        assertThat(context.conversationSummary()).isNull();
    }

    @Test
    void unknownSeniorIsRejected() {
        assertThatThrownBy(() -> contextService.assemble(
            UUID.randomUUID(), new ConversationContextRequest("", null, null, null, false, null)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("senior not found");
    }

    /** Robot utterances carry their trigger and priority, so T2 can split the volumes. */
    @Test
    void proactiveRobotMessageKeepsTriggerAndPriority() {
        Conversation conversation = conversationRepository.save(Conversation.open(senior.getId()));
        messageRepository.save(ConversationMessage.proactive(
            conversation.getId(), 1, "약 드셨어요?", OffsetDateTime.now(),
            MessageTriggerType.SCHEDULE, MessagePriority.MEDIUM));

        ConversationMessage stored = messageRepository.findAll().get(0);

        assertThat(stored.getTriggerType()).isEqualTo(MessageTriggerType.SCHEDULE);
        assertThat(stored.getPriority()).isEqualTo(MessagePriority.MEDIUM);
    }

    // ── 헬퍼 ────────────────────────────────────────────────────────────────

    private ConversationContextResponse assembleWithTopK(int topK) {
        return contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, topK, null, false, null));
    }

    private Memory saveMemory(String content, List<String> keywords, short importance) {
        Memory memory = Memory.create(senior.getId(), MemoryType.OTHER, content);
        memory.updateKeywords(keywords);
        memory.setImportance(importance);
        return memoryRepository.save(memory);
    }

    private DailyActivityMetric openTodayMetric() {
        LocalDate today = LocalDate.now(ZoneId.of(senior.getTimeZone()));
        DailyActivityMetric metric = DailyActivityMetric.openDay(senior.getId(), today);
        metric.recordSelfCare((short) 2, (short) 5, 420);
        return metric;
    }
}
