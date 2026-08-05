package com.ssafy.bomi.context;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

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
import com.ssafy.bomi.person.domain.KnownPerson;
import com.ssafy.bomi.person.repository.KnownPersonRepository;
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
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.test.web.servlet.MockMvc;

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
@AutoConfigureMockMvc
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
    @Autowired private KnownPersonRepository knownPersonRepository;
    @Autowired private MockMvc mockMvc;

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

    // ── S15P11E102-259: 이름표 오타 회귀 테스트 ─────────────────────────────

    /**
     * ConversationContextService 만 record_type 을 "CONDITION"·"SCHEDULE" 이라는
     * 존재하지 않는 값으로 찾고 있었다. 실제 값은 HEALTH_CONDITION·PERSONAL_SCHEDULE
     * 이고, 결과가 항상 0건이라 오류도 없이 조용히 빠졌다. 이 테스트가 그 경로를
     * 처음으로 태운다.
     */
    @Test
    void healthConditionAndPersonalScheduleRecordsReachTheContext() {
        careRecordRepository.save(CareRecord.create(
            senior.getId(), "HEALTH_CONDITION", Map.of("conditionName", "당뇨")));
        careRecordRepository.save(CareRecord.create(
            senior.getId(), "PERSONAL_SCHEDULE", Map.of("where", "미용실")));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.careRecords())
            .extracting(ConversationContextResponse.CareRecordItem::recordType)
            .containsExactlyInAnyOrder("HEALTH_CONDITION", "PERSONAL_SCHEDULE");
    }

    // ── S15P11E102-259: 나이·질환 ────────────────────────────────────────────

    @Test
    void profileCarriesAgeComputedFromBirthDateAndConfirmedConditions() {
        senior.changeBirthDate(LocalDate.now().minusYears(78));
        appUserRepository.save(senior);
        careRecordRepository.save(CareRecord.create(
            senior.getId(), "HEALTH_CONDITION", Map.of("conditionName", "고혈압")));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().age()).isEqualTo(78);
        assertThat(context.profile().conditions()).containsExactly("고혈압");
    }

    /** 생년월일이 비어 있으면 나이 줄만 빠지고 오류가 나지 않는다 (완료 조건). */
    @Test
    void missingBirthDateYieldsNullAgeWithoutError() {
        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().age()).isNull();
    }

    /** 질환도 다른 돌봄 기록과 같은 건강정보 동의 게이트를 따른다. */
    @Test
    void conditionsAreHiddenWithoutHealthDataConsent() {
        careRecordRepository.save(CareRecord.create(
            senior.getId(), "HEALTH_CONDITION", Map.of("conditionName", "당뇨")));
        senior.changeHealthDataConsent(ConsentStatus.DENIED);
        appUserRepository.save(senior);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().conditions()).isEmpty();
    }

    // ── S15P11E102-261: 개인차가 있어야 하는 값 세 가지 ──────────────────────

    /** 세 값이 모두 채워지면 문맥의 프로필에 실려야 한다(완료 조건). */
    @Test
    void profileCarriesWakeSleepTimeChronicPainAreaAndPreferredHospital() {
        senior.changeWakeTime(java.time.LocalTime.of(6, 30));
        senior.changeSleepTime(java.time.LocalTime.of(22, 30));
        senior.changeChronicPainArea("왼쪽 무릎");
        senior.changePreferredHospital("행복내과의원");
        appUserRepository.save(senior);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().wakeTime()).isEqualTo("06:30");
        assertThat(context.profile().sleepTime()).isEqualTo("22:30");
        assertThat(context.profile().chronicPainArea()).isEqualTo("왼쪽 무릎");
        assertThat(context.profile().preferredHospital()).isEqualTo("행복내과의원");
    }

    /** 세 값이 전부 비어 있는 어르신도 지금과 동일하게(오류 없이) 동작한다(완료 조건). */
    @Test
    void missingWakeSleepTimeChronicPainAreaAndPreferredHospitalYieldNullWithoutError() {
        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().wakeTime()).isNull();
        assertThat(context.profile().sleepTime()).isNull();
        assertThat(context.profile().chronicPainArea()).isNull();
        assertThat(context.profile().preferredHospital()).isNull();
    }

    // ── S15P11E102-253: 상위 동의 없이는 질문 자체를 만들지 않는다 ────────────

    /** 명시적으로 GRANTED 인 경우만 로봇이 동의 질문을 만들어도 된다고 본다(완료 조건). */
    @Test
    void profileExposesGuardianSharingConsentWhenGranted() {
        senior.changeGuardianSharingConsent(ConsentStatus.GRANTED);
        appUserRepository.save(senior);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().guardianSharingConsentGranted()).isTrue();
    }

    /**
     * DENIED 와 기본값(NOT_REQUESTED) 둘 다 "동의 아님"으로 취급한다 — "모르면
     * 동의로 본다"가 이 값에서 가장 위험한 방향의 실수다({@code isGranted} 와
     * 같은 원칙).
     */
    @Test
    void profileTreatsDeniedAndNotRequestedAsNotGranted() {
        ConversationContextResponse defaultContext = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));
        assertThat(defaultContext.profile().guardianSharingConsentGranted()).isFalse();

        senior.changeGuardianSharingConsent(ConsentStatus.DENIED);
        appUserRepository.save(senior);

        ConversationContextResponse deniedContext = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));
        assertThat(deniedContext.profile().guardianSharingConsentGranted()).isFalse();
    }

    // ── S15P11E102-260: known_person 이 회피 대상의 새 출처 ──────────────────

    /**
     * known_person 에 사망(is_deceased=TRUE)인 사람이 있으면 그 사람이 회피 대상이
     * 되고, 완료 조건대로 문구는 사실(死)이 아니라 금지문이어야 한다.
     */
    @Test
    void deceasedKnownPersonProducesAProhibitionNotAFact() {
        knownPersonRepository.save(KnownPerson.register(
            senior.getId(), null, "박정호", "배우자", true, "1년 전 지병으로 별세", null, null));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().avoidTopics()).hasSize(1);
        String phrase = context.profile().avoidTopics().get(0);
        assertThat(phrase).contains("박정호");
        // 회피 문구는 정보가 아니라 금지문이다 — 사망 사실이나 보호자 메모가
        // 그대로 새어 나오면 안 된다 (CLAUDE.md §8).
        assertThat(phrase).doesNotContain("별세").doesNotContain("사망").doesNotContain("지병");
    }

    /**
     * is_deceased 가 NULL(모름)인 사람도 TRUE 와 똑같이 먼저 언급되지 않아야 한다 —
     * 이 티켓의 완료 조건이 명시적으로 요구하는 안전한 기본값이다.
     */
    @Test
    void unknownSurvivalStatusIsTreatedAsAnAvoidTargetToo() {
        knownPersonRepository.save(KnownPerson.register(
            senior.getId(), null, "이영희", "친구", null, null, null, null));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().avoidTopics()).hasSize(1);
        assertThat(context.profile().avoidTopics().get(0)).contains("이영희");
    }

    /** 생존이 확인된(is_deceased=FALSE) 사람은 회피 대상이 아니다. */
    @Test
    void confirmedLivingKnownPersonIsNotAnAvoidTarget() {
        knownPersonRepository.save(KnownPerson.register(
            senior.getId(), null, "김민수", "아들", false, null, false, "주 1회"));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().avoidTopics()).isEmpty();
    }

    /**
     * known_person 이 하나라도 있으면 그 목록이 우선한다 — jsonb 경로는 known_person
     * 이 <em>전혀</em> 없을 때만 쓰는 호환 폴백이다(완료 조건).
     */
    @Test
    void knownPersonListTakesPriorityOverTheLegacyJsonbList() {
        // setUpSenior() 가 이미 conversation_preferences.avoid_topics = ["남편 사망"] 을
        // 심어 두었다. known_person 이 생기면 이 jsonb 값은 더 이상 쓰이지 않는다.
        knownPersonRepository.save(KnownPerson.register(
            senior.getId(), null, "박정호", "배우자", true, null, null, null));

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("", null, null, null, false, null));

        assertThat(context.profile().avoidTopics()).doesNotContain("남편 사망");
        assertThat(context.profile().avoidTopics().get(0)).contains("박정호");
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
     * A guardian must never receive raw utterances or summary text, even though the
     * senior's own conversation has both (S15P11E102-254, CLAUDE.md §9 T4).
     *
     * <p>Unlike memories, {@code conversation_message} and {@code conversation_summary}
     * carry no per-row visibility column — "PRIVATE unless shared" does not apply here.
     * The only safe default is "a guardian request sees no raw content at all", so this
     * pins {@code forGuardian} in {@code ConversationContextService.assemble} rather than
     * relying on the memory visibility filter to somehow also cover these two fields.</p>
     */
    @Test
    void guardianRequestNeverSeesRawMessagesOrSummaries() {
        Conversation conversation = conversationRepository.save(Conversation.open(senior.getId()));
        messageRepository.save(ConversationMessage.reactive(
            conversation.getId(), 1, MessageRole.SENIOR, "무릎이 아파", OffsetDateTime.now()));
        summaryRepository.save(ConversationSummary.forConversation(
            senior.getId(), conversation.getId(),
            OffsetDateTime.now().minusHours(1), OffsetDateTime.now(), "지금 대화 요약", 1));

        UUID guardianId = appUserRepository.save(AppUser.create("GUARDIAN", "딸")).getId();
        careRelationshipRepository.save(CareRelationship.create(
            senior.getId(), guardianId, RelationshipPriority.SECONDARY));

        ConversationContextResponse robotView = contextService.assemble(
            senior.getId(),
            new ConversationContextRequest("", conversation.getId(), null, null, false, null));
        ConversationContextResponse guardianView = contextService.assemble(
            senior.getId(),
            new ConversationContextRequest("", conversation.getId(), null, null, false, guardianId));

        // 로봇이 어르신과 말할 때는 그대로 실린다 — 대조군.
        assertThat(robotView.recentMessages()).isNotEmpty();
        assertThat(robotView.conversationSummary()).isEqualTo("지금 대화 요약");

        // 보호자 요청은 원문·요약 어느 쪽도 받지 않는다.
        assertThat(guardianView.recentMessages()).isEmpty();
        assertThat(guardianView.conversationSummary()).isNull();
        assertThat(guardianView.relevantSummaries()).isEmpty();
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
        saveMemory("무릎이 아프다", List.of("무릎"), (short) 3);
        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, null, null, false, null));

        assertThat(context.availability().semanticSearch()).isFalse();
        assertThat(context.availability().notes())
            .anySatisfy(note -> assertThat(note).contains("semantic search unavailable"));
        assertThat(context.retrieval().semanticRequested()).isTrue();
        assertThat(context.retrieval().semanticUsed()).isFalse();
        assertThat(context.retrieval().fallbackReason()).isEqualTo("semantic_unavailable");
        assertThat(context.retrieval().hitCount()).isZero();
        assertThat(context.retrieval().latencyMs()).isZero();
    }

    @Test
    void noCandidatesIsNotReportedAsAFailedSemanticSearch() {
        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, null, null, false, null));

        assertThat(context.retrieval().semanticRequested()).isFalse();
        assertThat(context.retrieval().semanticUsed()).isFalse();
        assertThat(context.retrieval().fallbackReason()).isEqualTo("no_candidates");
    }

    @Test
    void documentsAreSearchedOnlyWhenRequestedAndCarryTraceableMetadata() {
        ConversationContextResponse withoutFlag = contextService.assemble(
            senior.getId(), new ConversationContextRequest("복지", null, null, null, false, null));
        ConversationContextResponse withFlag = contextService.assemble(
            senior.getId(), new ConversationContextRequest("복지", null, null, null, true, null));

        assertThat(withoutFlag.documents()).isEmpty();
        assertThat(withoutFlag.retrieval().documentRequested()).isFalse();
        assertThat(withoutFlag.availability().documentCorpus()).isTrue();
        assertThat(withoutFlag.availability().notes())
            .noneSatisfy(note -> assertThat(note).contains("document corpus"));

        assertThat(withFlag.documents()).isNotEmpty()
            .allSatisfy(document -> {
                assertThat(document.source()).isEqualTo("복지로");
                assertThat(document.version()).isNotBlank();
                assertThat(document.chunkId()).startsWith("bokjiro-");
                assertThat(document.citation()).isNotBlank();
                assertThat(document.url()).startsWith("https://www.bokjiro.go.kr/");
            });
        assertThat(withFlag.availability().documentCorpus()).isTrue();
        assertThat(withFlag.retrieval().documentRequested()).isTrue();
        assertThat(withFlag.retrieval().documentUsed()).isTrue();
        assertThat(withFlag.retrieval().documentFallbackReason()).isNull();
        assertThat(withFlag.retrieval().documentHitCount())
            .isEqualTo(withFlag.documents().size());
        assertThat(withFlag.availability().notes())
            .noneSatisfy(note -> assertThat(note).contains("document corpus"));
    }

    @Test
    void welfareQuestionCarriesCorpusEvidenceThroughTheRealHttpEndpoint() throws Exception {
        mockMvc.perform(post("/api/v1/seniors/{seniorId}/conversation-context", senior.getId())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "query": "복지제도 알려줘",
                      "includeDocuments": true
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.availability.documentCorpus").value(true))
            .andExpect(jsonPath("$.retrieval.documentRequested").value(true))
            .andExpect(jsonPath("$.retrieval.documentUsed").value(true))
            .andExpect(jsonPath("$.retrieval.documentHitCount").value(3))
            .andExpect(jsonPath("$.documents[0].source").value("복지로"))
            .andExpect(jsonPath("$.documents[0].version").isNotEmpty())
            .andExpect(jsonPath("$.documents[0].chunkId").isNotEmpty())
            .andExpect(jsonPath("$.documents[0].citation").isNotEmpty())
            .andExpect(jsonPath("$.documents[0].url").value(
                org.hamcrest.Matchers.startsWith("https://www.bokjiro.go.kr/")));
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

    // ── S15P11E102-262: 최근에 쓴 기억은 감점된다 (같은 회상 반복 방지) ─────────

    /**
     * 완료 조건: "최근에 사용된 기억이 감점되어, 같은 기억이 연속으로 뽑히지
     * 않는 것을 테스트로 확인합니다".
     *
     * <p>두 기억을 관련성·중요도가 완전히 동일하게 심는다. 어느 쪽이 먼저 뽑히든,
     * assemble 이 그 기억의 last_used_at 을 갱신하므로 다음 호출에서는 반드시
     * 나머지 하나가 뽑혀야 한다 — 고친 방향(최근 사용 = 감점)이 실제로 반영됐다는
     * 증거다. 고치기 전 코드(최근 사용 = 가점)였다면 같은 기억이 계속 뽑혔을
     * 것이다.</p>
     */
    @Test
    void recentlyUsedMemoriesAreDeprioritizedNextRound() {
        // memoryTopKMin 이 3 이라(§7 clampMemoryTopK) 4건을 심어 topK=3 으로 요청한다 —
        // 그래야 '이번엔 뽑히지 않은 한 건'이 반드시 생겨서, 감점 효과를 관찰할 수 있다.
        List<Memory> memories = new ArrayList<>();
        for (int index = 0; index < 4; index++) {
            memories.add(saveMemory("기억 " + index, List.of("무릎"), (short) 3));
        }

        ConversationContextResponse round1 = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, 3, null, false, null));
        List<UUID> round1Ids = round1.memories().stream()
            .map(ConversationContextResponse.MemoryItem::id).toList();
        assertThat(round1Ids).hasSize(3);

        UUID leftOutOfRound1 = memories.stream().map(Memory::getId)
            .filter(id -> !round1Ids.contains(id)).findFirst().orElseThrow();

        ConversationContextResponse round2 = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, 3, null, false, null));
        List<UUID> round2Ids = round2.memories().stream()
            .map(ConversationContextResponse.MemoryItem::id).toList();

        // 1라운드에서 뽑혔던 세 기억은 이제 감점됐고, 아직 한 번도 안 쓰인 네 번째
        // 기억은 감점이 없다 — 그래서 2라운드에는 반드시 들어와야 한다. 고치기 전
        // 코드(최근 사용 = 가점)였다면 1라운드의 세 기억이 그대로 다시 뽑혔을 것이다.
        assertThat(round2Ids).contains(leftOutOfRound1);
    }

    /**
     * markUsed 호출이 실제로 last_used_at 을 채우는지 리포지토리 레벨에서 직접
     * 확인한다. 서비스 테스트만으로는 "선택이 바뀌었다"까지만 보이고, "그 이유가
     * 정말 last_used_at 갱신 때문인가"는 이 테스트가 답한다.
     */
    @Test
    void assembleStampsLastUsedAtOnSelectedMemories() {
        Memory memory = saveMemory("기억", List.of("무릎"), (short) 3);
        assertThat(memory.getLastUsedAt()).isNull();

        assembleWithTopK(1);

        Memory reloaded = memoryRepository.findById(memory.getId()).orElseThrow();
        assertThat(reloaded.getLastUsedAt()).isNotNull();
    }

    /** 한 번도 쓰인 적 없는 기억은 감점되지 않는다 — 회상 씨앗이 영원히 묻히면 안 된다. */
    @Test
    void neverUsedMemoryIsNotPenalized() {
        Memory neverUsed = saveMemory("아직 안 꺼낸 기억", List.of("무릎"), (short) 3);

        ConversationContextResponse context = contextService.assemble(
            senior.getId(), new ConversationContextRequest("무릎", null, 3, null, false, null));

        assertThat(context.memories()).extracting(ConversationContextResponse.MemoryItem::id)
            .contains(neverUsed.getId());
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
