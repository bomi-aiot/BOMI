package com.ssafy.bomi.context.application;

import com.ssafy.bomi.activity.domain.DailyActivityMetric;
import com.ssafy.bomi.activity.repository.DailyActivityMetricRepository;
import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import com.ssafy.bomi.care.repository.CareRecordRepository;
import com.ssafy.bomi.context.api.ConversationContextRequest;
import com.ssafy.bomi.context.api.ConversationContextResponse;
import com.ssafy.bomi.context.api.ConversationContextResponse.Availability;
import com.ssafy.bomi.context.api.ConversationContextResponse.CareRecordItem;
import com.ssafy.bomi.context.api.ConversationContextResponse.DocumentItem;
import com.ssafy.bomi.context.api.ConversationContextResponse.MemoryItem;
import com.ssafy.bomi.context.api.ConversationContextResponse.RawMessage;
import com.ssafy.bomi.context.api.ConversationContextResponse.SeniorProfile;
import com.ssafy.bomi.context.api.ConversationContextResponse.SummaryItem;
import com.ssafy.bomi.context.api.ConversationContextResponse.TodayState;
import com.ssafy.bomi.context.config.ContextAssemblyProperties;
import com.ssafy.bomi.conversation.domain.ConversationMessage;
import com.ssafy.bomi.conversation.domain.ConversationSummary;
import com.ssafy.bomi.conversation.repository.ConversationMessageRepository;
import com.ssafy.bomi.conversation.repository.ConversationSummaryRepository;
import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.relationship.domain.CareRelationship;
import com.ssafy.bomi.relationship.domain.RelationshipPriority;
import com.ssafy.bomi.relationship.domain.RelationshipStatus;
import com.ssafy.bomi.relationship.repository.CareRelationshipRepository;
import com.ssafy.bomi.user.domain.AppUser;
import com.ssafy.bomi.user.domain.ConsentStatus;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Assembles one turn's conversation context, per MVP ERD §9.
 *
 * <p>This service is the API seam described in CLAUDE.md §5. This side is the authority
 * on facts and retrieval — the pre-filter, the reranking, and the consent gates. The
 * robot is the authority on timing and delivery. The robot never runs a vector search
 * of its own, which is also what structurally enforces "do not vectorise the profile".</p>
 *
 * <p>Two rules shape almost every method here:</p>
 * <ul>
 *   <li><strong>Exact lookup for anything safety-critical.</strong> Profile, medication,
 *       schedule, and the avoid-list are fetched by key, never by similarity. Embeddings
 *       rank "혈압약" and "혈당약" as nearly identical, and returning the wrong one is a
 *       dangerous answer rather than a slightly worse one (CLAUDE.md §8).</li>
 *   <li><strong>Never attach everything.</strong> The ERD says not to include every
 *       daily summary and every memory each turn. An overloaded prompt is what makes a
 *       robot answer with three facts at once, which by ear nobody can follow.</li>
 * </ul>
 */
@Service
public class ConversationContextService {

    private static final Logger log = LoggerFactory.getLogger(ConversationContextService.class);

    /**
     * Key in {@code app_user.conversation_preferences} holding topics to avoid.
     *
     * <p>Read deterministically and passed to the prompt as a prohibition. Probabilistic
     * recall is unacceptable here: surfacing a deceased spouse as if alive is one of the
     * worst failures this product can produce (CLAUDE.md §8, §17.5).</p>
     */
    private static final String AVOID_TOPICS_KEY = "avoid_topics";

    /**
     * Care-record types that answer "what am I supposed to take / when is my appointment".
     *
     * <p>Observations are excluded on purpose. They are the raw material of the daily
     * metrics, not something to read back to the senior mid-conversation.</p>
     */
    private static final Set<String> HEALTH_RECORD_TYPES =
        Set.of("MEDICATION", "MEDICATION_SCHEDULE", "ALLERGY", "CONDITION");

    private static final Set<String> SCHEDULE_RECORD_TYPES =
        Set.of("APPOINTMENT", "SCHEDULE");

    private final AppUserRepository appUserRepository;
    private final CareRelationshipRepository careRelationshipRepository;
    private final DailyActivityMetricRepository dailyActivityMetricRepository;
    private final ConversationMessageRepository conversationMessageRepository;
    private final ConversationSummaryRepository conversationSummaryRepository;
    private final MemoryRepository memoryRepository;
    private final CareRecordRepository careRecordRepository;
    private final MemorySemanticSearch semanticSearch;
    private final DocumentCorpusSearch documentSearch;
    private final ContextAssemblyProperties properties;

    public ConversationContextService(
        AppUserRepository appUserRepository,
        CareRelationshipRepository careRelationshipRepository,
        DailyActivityMetricRepository dailyActivityMetricRepository,
        ConversationMessageRepository conversationMessageRepository,
        ConversationSummaryRepository conversationSummaryRepository,
        MemoryRepository memoryRepository,
        CareRecordRepository careRecordRepository,
        MemorySemanticSearch semanticSearch,
        DocumentCorpusSearch documentSearch,
        ContextAssemblyProperties properties
    ) {
        this.appUserRepository = appUserRepository;
        this.careRelationshipRepository = careRelationshipRepository;
        this.dailyActivityMetricRepository = dailyActivityMetricRepository;
        this.conversationMessageRepository = conversationMessageRepository;
        this.conversationSummaryRepository = conversationSummaryRepository;
        this.memoryRepository = memoryRepository;
        this.careRecordRepository = careRecordRepository;
        this.semanticSearch = semanticSearch;
        this.documentSearch = documentSearch;
        this.properties = properties;
    }

    /**
     * Builds the six-part context for one senior and one turn.
     *
     * @throws IllegalArgumentException if the senior does not exist, or if a guardian was
     *     named but has no active relationship with that senior
     */
    @Transactional(readOnly = true)
    public ConversationContextResponse assemble(UUID seniorId, ConversationContextRequest request) {
        AppUser senior = appUserRepository.findById(seniorId)
            .orElseThrow(() -> new IllegalArgumentException("senior not found: " + seniorId));

        Set<MemoryVisibility> allowedVisibilities = resolveVisibility(seniorId, request);

        // 가용성은 '능력'을 설명하는 값이므로 조회 결과와 무관하게 먼저 정한다.
        // 기억이 0건이라 조회를 건너뛰었다는 이유로 "의미 검색을 못 했다"는 사실이
        // 사라지면, 호출부는 빈 목록을 '관련된 기억이 없음'으로 오해한다.
        List<String> notes = new ArrayList<>();
        if (!semanticSearch.isAvailable()) {
            notes.add("semantic search unavailable; memories ranked by keyword overlap, "
                + "importance and recency only (S15P11E102-218)");
        }

        String query = request.queryOrEmpty();
        Set<String> queryTerms = tokenize(query);

        List<MemoryItem> memories = selectMemories(seniorId, query, queryTerms, allowedVisibilities,
            clampMemoryTopK(request.memoryTopK()), notes);

        return new ConversationContextResponse(
            buildProfile(senior),
            loadTodayState(senior),
            loadRecentMessages(request.conversationId(),
                clampRecentMessages(request.recentMessageLimit())),
            loadConversationSummary(request.conversationId()),
            selectRelevantSummaries(seniorId, request.conversationId(), queryTerms),
            memories,
            selectCareRecords(senior, queryTerms),
            loadDocuments(request, query, notes),
            new Availability(semanticSearch.isAvailable(), documentSearch.isAvailable(), notes)
        );
    }

    // ── 1. 프로필·선호 (정확 조회) ────────────────────────────────────────────

    private SeniorProfile buildProfile(AppUser senior) {
        Map<String, Object> preferences = senior.getConversationPreferences() == null
            ? Map.of()
            : new HashMap<>(senior.getConversationPreferences());

        return new SeniorProfile(
            senior.getId(),
            senior.getName(),
            senior.getPreferredName(),
            senior.getTimeZone(),
            senior.getQuietHoursStart().toString(),
            senior.getQuietHoursEnd().toString(),
            preferences,
            extractAvoidTopics(preferences)
        );
    }

    /**
     * Pulls the avoid-list out of the preferences JSON.
     *
     * <p>Defensive about shape because this value is written by two channels (app and
     * robot onboarding) and a malformed entry must not take the endpoint down. Failing
     * closed here means returning an empty list, and that is the dangerous direction —
     * so a surprise shape is logged loudly rather than swallowed.</p>
     */
    private List<String> extractAvoidTopics(Map<String, Object> preferences) {
        Object raw = preferences.get(AVOID_TOPICS_KEY);
        if (raw == null) {
            return List.of();
        }
        if (raw instanceof List<?> list) {
            return list.stream().filter(java.util.Objects::nonNull).map(Object::toString).toList();
        }
        if (raw instanceof String single && !single.isBlank()) {
            return List.of(single);
        }
        log.warn("unexpected {} shape in conversation_preferences: {}",
            AVOID_TOPICS_KEY, raw.getClass().getName());
        return List.of();
    }

    // ── 2. 오늘 상태 ──────────────────────────────────────────────────────────

    /**
     * Today's aggregates, using the senior's own local date.
     *
     * <p>Computing "today" in UTC would put anything said near midnight on the wrong
     * day, which is how a trend report ends up describing the wrong night's sleep.</p>
     */
    private TodayState loadTodayState(AppUser senior) {
        LocalDate today = LocalDate.now(resolveZone(senior));
        return dailyActivityMetricRepository
            .findBySeniorIdAndMetricDate(senior.getId(), today)
            .map(this::toTodayState)
            .orElse(null);
    }

    private TodayState toTodayState(DailyActivityMetric metric) {
        return new TodayState(
            metric.getMetricDate(),
            metric.getMedicationTakenCount(),
            metric.getMedicationScheduledCount(),
            metric.getMealCount(),
            metric.getWaterIntakeCount(),
            metric.getSleepMinutes(),
            metric.getMoodScore(),
            metric.getOutingCount()
        );
    }

    private ZoneId resolveZone(AppUser senior) {
        try {
            return ZoneId.of(senior.getTimeZone());
        } catch (RuntimeException error) {
            // 시간대가 깨졌다고 문맥 조립 전체를 실패시키지는 않는다. 다만 조용히 UTC 로
            // 넘어가면 '오늘'이 몇 시간 밀리므로 반드시 기록한다.
            log.warn("invalid time_zone for senior {}: {}", senior.getId(), senior.getTimeZone());
            return ZoneId.systemDefault();
        }
    }

    // ── 3. 현재 대화 최근 Raw ─────────────────────────────────────────────────

    private List<RawMessage> loadRecentMessages(UUID conversationId, int limit) {
        if (conversationId == null) {
            return List.of();
        }
        List<ConversationMessage> newestFirst = conversationMessageRepository
            .findByConversationIdOrderByOccurredAtDescSequenceNoDesc(
                conversationId, PageRequest.of(0, limit));

        // 프롬프트는 시간순으로 읽어야 하고, DB 는 최신부터 찾는 편이 싸다. 그래서
        // 조회는 역순으로 하고 여기서 되돌린다.
        List<RawMessage> chronological = new ArrayList<>(newestFirst.size());
        for (int index = newestFirst.size() - 1; index >= 0; index--) {
            ConversationMessage message = newestFirst.get(index);
            chronological.add(new RawMessage(
                message.getRole().name(), message.getContent(), message.getOccurredAt()));
        }
        return chronological;
    }

    // ── 4. 요약 ───────────────────────────────────────────────────────────────

    private String loadConversationSummary(UUID conversationId) {
        if (conversationId == null) {
            return null;
        }
        return conversationSummaryRepository
            .findByConversationIdAndSupersededByIdIsNull(conversationId)
            .map(ConversationSummary::getContent)
            .orElse(null);
    }

    /**
     * A few other summaries, chosen by keyword relevance and then recency.
     *
     * <p>The current conversation's own summary is excluded — it is returned separately,
     * and including it twice would spend prompt budget repeating itself.</p>
     */
    private List<SummaryItem> selectRelevantSummaries(
        UUID seniorId, UUID currentConversationId, Set<String> queryTerms) {

        // 후보를 한도의 몇 배만 읽는다. 전부 읽으면 문맥 과적재 방지의 취지가 무너지고,
        // 한도만큼만 읽으면 관련성 판단의 여지가 없다.
        int candidateLimit = Math.max(properties.getSummaryLimit() * 4, properties.getSummaryLimit());
        List<ConversationSummary> candidates = conversationSummaryRepository
            .findRecentBySenior(seniorId, PageRequest.of(0, candidateLimit));

        return candidates.stream()
            .filter(summary -> currentConversationId == null
                || !currentConversationId.equals(summary.getConversationId()))
            .sorted(Comparator.comparingDouble(
                (ConversationSummary summary) ->
                    keywordOverlap(queryTerms, tokenize(summary.getContent())))
                .reversed()
                .thenComparing(ConversationSummary::getPeriodEndedAt, Comparator.reverseOrder()))
            .limit(properties.getSummaryLimit())
            .map(summary -> new SummaryItem(
                summary.getId(),
                summary.getSummaryType().name(),
                summary.getContent(),
                summary.getPeriodStartedAt(),
                summary.getPeriodEndedAt()))
            .toList();
    }

    // ── 5. 장기 기억 (선필터 + 재정렬) ────────────────────────────────────────

    /**
     * Selects the top-k memories: pre-filter first, then rerank.
     *
     * <p>Order matters. The pre-filter is authoritative and runs against this database,
     * so a memory whose visibility or lifecycle changed after it was indexed can never
     * be returned on the strength of a stale copy in the vector store. Semantic hits
     * only contribute a <em>score</em>; they never add rows.</p>
     *
     * <p>Reranking is similarity × importance × recency, as the ERD requires. Without
     * all three, a knee complaint from six months ago outranks yesterday's.</p>
     */
    private List<MemoryItem> selectMemories(
        UUID seniorId,
        String query,
        Set<String> queryTerms,
        Set<MemoryVisibility> allowedVisibilities,
        int topK,
        List<String> notes
    ) {
        List<Memory> retrievable = memoryRepository.findRetrievable(seniorId, allowedVisibilities);
        if (retrievable.isEmpty()) {
            return List.of();
        }

        Map<UUID, Double> similarities = loadSimilarities(seniorId, query, topK);

        OffsetDateTime now = OffsetDateTime.now();
        return retrievable.stream()
            .map(memory -> new ScoredMemory(memory, score(memory, queryTerms, similarities, now)))
            .sorted(Comparator.comparingDouble(ScoredMemory::score).reversed())
            .limit(topK)
            .map(scored -> new MemoryItem(
                scored.memory().getId(),
                scored.memory().getMemoryType().name(),
                scored.memory().getContent(),
                scored.memory().getKeywords() == null ? List.of() : scored.memory().getKeywords(),
                scored.memory().getImportance(),
                scored.memory().getLastConfirmedAt(),
                scored.score()))
            .toList();
    }

    private record ScoredMemory(Memory memory, double score) {}

    /** Similarity scores by memory id, or empty when semantic search cannot run. */
    private Map<UUID, Double> loadSimilarities(UUID seniorId, String query, int topK) {
        if (!semanticSearch.isAvailable()) {
            // 미가용 사실은 assemble 에서 이미 notes 에 기록했다. 여기서는 조용히
            // 빈 결과를 돌려주고, 점수는 키워드·중요도·최근성으로 계산된다.
            return Map.of();
        }
        if (query.isBlank()) {
            // 발화가 없는 턴(예: 스케줄 제안)은 비교 기준이 없다. 그때는 중요도와
            // 최근성만으로 고르는 것이 맞고, 빈 질의로 벡터를 조회할 이유가 없다.
            return Map.of();
        }

        // 필요한 개수보다 넉넉히 받는다. 선필터가 일부를 걷어내므로, 정확히 topK 만
        // 받으면 필터 후 개수가 부족해진다.
        Map<UUID, Double> similarities = new HashMap<>();
        semanticSearch.search(seniorId, query, topK * 3)
            .forEach(hit -> similarities.put(hit.memoryId(), hit.similarity()));
        return similarities;
    }

    /**
     * similarity × importance × recency.
     *
     * <p>Multiplied rather than added so a memory has to be at least somewhat good on
     * every axis. Adding would let a very old but very important memory dominate every
     * turn regardless of what the senior actually said.</p>
     */
    private double score(
        Memory memory,
        Set<String> queryTerms,
        Map<UUID, Double> similarities,
        OffsetDateTime now
    ) {
        Double semantic = similarities.get(memory.getId());
        double relevance = semantic != null
            ? semantic
            : keywordRelevance(queryTerms, memory);

        // importance 는 1~5 이고, 비어 있으면 중간값으로 취급한다. 없는 값을 0 으로
        // 보면 아직 중요도를 매기지 않은 기억이 영원히 선택되지 않는다.
        short importance = memory.getImportance() == null ? (short) 3 : memory.getImportance();
        double importanceWeight = importance / 5.0;

        return relevance * importanceWeight * recencyWeight(memory, now);
    }

    private double keywordRelevance(Set<String> queryTerms, Memory memory) {
        Set<String> memoryTerms = new HashSet<>(tokenize(memory.getContent()));
        if (memory.getKeywords() != null) {
            memory.getKeywords().forEach(keyword -> memoryTerms.addAll(tokenize(keyword)));
        }
        double overlap = keywordOverlap(queryTerms, memoryTerms);
        // 겹치는 단어가 없어도 0 으로 떨구지 않는다. 0 이면 그 기억은 importance 와
        // recency 가 아무리 높아도 절대 선택되지 않고, 검색이 조용히 '아무것도
        // 기억하지 못하는' 상태가 된다.
        return properties.getRelevanceFloor()
            + (1.0 - properties.getRelevanceFloor()) * overlap;
    }

    /**
     * Exponential decay on the most recent confirmation or use.
     *
     * <p>Uses {@code lastConfirmedAt} or {@code lastUsedAt} rather than creation time:
     * what matters is when we last knew this to be true, not when it was first written.</p>
     */
    private double recencyWeight(Memory memory, OffsetDateTime now) {
        OffsetDateTime reference = latest(
            memory.getLastConfirmedAt(), memory.getLastUsedAt(), memory.getFirstObservedAt());
        if (reference == null) {
            // 시각 정보가 아예 없으면 최근성으로 벌점을 주지 않는다. 벌점을 주면
            // 온보딩으로 들어온 오래된 사실이 전부 밀려난다.
            return 1.0;
        }
        long days = Math.max(0, ChronoUnit.DAYS.between(reference, now));
        return Math.pow(0.5, (double) days / properties.getRecencyHalfLifeDays());
    }

    private OffsetDateTime latest(OffsetDateTime... candidates) {
        return Arrays.stream(candidates)
            .filter(java.util.Objects::nonNull)
            .max(Comparator.naturalOrder())
            .orElse(null);
    }

    // ── 6. 동의된 돌봄 기록 ───────────────────────────────────────────────────

    /**
     * Care records the senior consented to sharing with the robot, filtered by relevance.
     *
     * <p>Consent is checked per category, not once. Health and schedule are separate
     * consents in {@code app_user}, and a senior who agreed to medication reminders has
     * not thereby agreed to have appointments read out.</p>
     */
    private List<CareRecordItem> selectCareRecords(AppUser senior, Set<String> queryTerms) {
        Set<String> permittedTypes = new HashSet<>();
        if (isGranted(senior.getHealthDataConsentStatus())) {
            permittedTypes.addAll(HEALTH_RECORD_TYPES);
        }
        if (isGranted(senior.getScheduleConsentStatus())) {
            permittedTypes.addAll(SCHEDULE_RECORD_TYPES);
        }
        if (permittedTypes.isEmpty()) {
            return List.of();
        }

        List<CareRecord> records = careRecordRepository.findBySeniorIdAndStatusAndRecordTypeIn(
            senior.getId(), CareRecordStatus.ACTIVE, permittedTypes);

        return records.stream()
            .sorted(Comparator.comparingDouble(
                (CareRecord record) -> careRecordRelevance(queryTerms, record)).reversed())
            .limit(properties.getCareRecordLimit())
            .map(record -> new CareRecordItem(
                record.getId(),
                record.getRecordType(),
                record.getStatus().name(),
                record.getDetails() == null ? Map.of() : new HashMap<>(record.getDetails())))
            .toList();
    }

    private double careRecordRelevance(Set<String> queryTerms, CareRecord record) {
        Set<String> terms = new HashSet<>(tokenize(record.getRecordType()));
        if (record.getDetails() != null) {
            record.getDetails().forEach((key, value) -> {
                terms.addAll(tokenize(key));
                if (value != null) {
                    terms.addAll(tokenize(value.toString()));
                }
            });
        }
        return keywordOverlap(queryTerms, terms);
    }

    private boolean isGranted(ConsentStatus status) {
        return status == ConsentStatus.GRANTED;
    }

    // ── 문서 RAG (info 인텐트에서만) ──────────────────────────────────────────

    private List<DocumentItem> loadDocuments(
        ConversationContextRequest request, String query, List<String> notes) {

        if (!request.wantsDocuments()) {
            return List.of();
        }
        if (!documentSearch.isAvailable()) {
            notes.add("document corpus not built yet; no documents searched");
            return List.of();
        }
        return documentSearch.search(query, properties.getSummaryLimit()).stream()
            .map(hit -> new DocumentItem(hit.title(), hit.content(), hit.sourceRef()))
            .toList();
    }

    // ── 가시성 결정 ───────────────────────────────────────────────────────────

    /**
     * Which memory visibilities the requester may see.
     *
     * <p>No guardian named means the robot is assembling context to talk <em>to</em> the
     * senior, so everything including {@code PRIVATE} is usable. {@code PRIVATE} is the
     * senior-only value — it is what makes T4 ("just between us") real, and T4 has to be
     * real or the senior stops confiding and the emotional pillar dies (CLAUDE.md §9).</p>
     *
     * <p>A guardian sees strictly less, and only through an {@code ACTIVE} relationship.
     * A {@code SECONDARY} guardian does not see what was shared with the primary only.</p>
     */
    private Set<MemoryVisibility> resolveVisibility(
        UUID seniorId, ConversationContextRequest request) {

        UUID guardianId = request.requesterGuardianId();
        if (guardianId == null) {
            return EnumSet.allOf(MemoryVisibility.class);
        }

        Optional<CareRelationship> relationship = careRelationshipRepository
            .findBySeniorIdAndGuardianIdAndStatus(seniorId, guardianId, RelationshipStatus.ACTIVE);
        if (relationship.isEmpty()) {
            // 조용히 빈 목록을 주지 않고 거절한다. 관계가 없는데 결과가 비어 있으면
            // 호출부는 "공유된 기억이 없다"로 오해하고, 그 오해는 권한 버그를 숨긴다.
            throw new IllegalArgumentException(
                "no active care relationship: senior=" + seniorId + " guardian=" + guardianId);
        }

        if (relationship.get().getPriority() == RelationshipPriority.PRIMARY) {
            return EnumSet.of(
                MemoryVisibility.SHARED_WITH_PRIMARY, MemoryVisibility.SHARED_WITH_GUARDIANS);
        }
        return EnumSet.of(MemoryVisibility.SHARED_WITH_GUARDIANS);
    }

    // ── 한도 정리와 토큰화 ────────────────────────────────────────────────────

    /**
     * Clamps the requested memory count into the configured range.
     *
     * <p>Clamps rather than rejects because the robot lowers its own top-k when the
     * network or the device is under pressure. That is the designed degradation path, so
     * a small number must not come back as a 400 (CLAUDE.md §18).</p>
     */
    private int clampMemoryTopK(Integer requested) {
        int value = requested == null ? properties.getMemoryTopKDefault() : requested;
        return clamp(value, properties.getMemoryTopKMin(), properties.getMemoryTopKMax());
    }

    private int clampRecentMessages(Integer requested) {
        int value = requested == null ? properties.getRecentMessageDefault() : requested;
        return clamp(value, properties.getRecentMessageMin(), properties.getRecentMessageMax());
    }

    // Math.clamp 은 Java 21 부터다. 이 프로젝트의 툴체인은 17 이다.
    private static int clamp(int value, int min, int max) {
        return Math.max(min, Math.min(max, value));
    }

    /**
     * Splits text into comparable terms.
     *
     * <p>Deliberately crude: lowercase, split on non-letter/digit, drop very short
     * tokens. This is a stand-in for semantic similarity, not a Korean analyser, and
     * pretending otherwise would hide how shallow retrieval currently is. Korean
     * particles mean "무릎이" and "무릎" do not match here — one more reason the vector
     * store in S15P11E102-218 matters.</p>
     */
    private Set<String> tokenize(String text) {
        if (text == null || text.isBlank()) {
            return Set.of();
        }
        Set<String> terms = new HashSet<>();
        for (String token : text.toLowerCase(Locale.ROOT).split("[^\\p{L}\\p{N}]+")) {
            if (token.length() > 1) {
                terms.add(token);
            }
        }
        return terms;
    }

    /** Fraction of query terms present in the candidate. 0.0 when either side is empty. */
    private double keywordOverlap(Set<String> queryTerms, Set<String> candidateTerms) {
        if (queryTerms.isEmpty() || candidateTerms.isEmpty()) {
            return 0.0;
        }
        long matches = queryTerms.stream().filter(candidateTerms::contains).count();
        return (double) matches / queryTerms.size();
    }
}
