package com.ssafy.bomi.context.api;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * One turn's assembled context — the six kinds of MVP ERD §9, in one response.
 *
 * <p>The point of returning all of it together is that the robot must not do retrieval
 * itself. This side owns facts and search; the robot owns timing and delivery
 * (CLAUDE.md §5). A single call also means one network round trip inside a
 * two-second turn budget instead of six.</p>
 *
 * <p>The sections are separate rather than pre-rendered into one blob because the
 * prompt builder assembles them in a specific order, and the avoid-list has to be
 * injected as a prohibition rather than as information (CLAUDE.md §16).</p>
 *
 * @param profile exact-lookup facts. Never vector-searched: "혈압약" and "혈당약" are
 *     near-identical as embeddings, and a medication answer must be exact.
 * @param todayState today's aggregates, or {@code null} if nothing was recorded.
 * @param recentMessages the raw tail in chronological order.
 * @param conversationSummary the current conversation's own summary, if any.
 * @param relevantSummaries other summaries worth attaching. Never all of them.
 * @param memories long-term memories that passed the pre-filter, best first.
 * @param careRecords consented, relevant care records.
 * @param documents reference corpus chunks; empty unless requested.
 * @param availability what could and could not actually be searched.
 */
public record ConversationContextResponse(
    SeniorProfile profile,
    TodayState todayState,
    List<RawMessage> recentMessages,
    String conversationSummary,
    List<SummaryItem> relevantSummaries,
    List<MemoryItem> memories,
    List<CareRecordItem> careRecords,
    List<DocumentItem> documents,
    Availability availability
) {

    /**
     * Exact-lookup profile and preferences.
     *
     * @param avoidTopics topics that must be treated as a <strong>prohibition</strong>
     *     in the prompt, not as information. Given as facts, a model will happily bring
     *     up a deceased spouse. Enforced deterministically, never by similarity.
     * @param quietHoursStart local time, to be read with {@code timeZone}. The window
     *     normally crosses midnight, so start may be later than end.
     * @param age computed from {@code app_user.birth_date} at assembly time, not stored
     *     (S15P11E102-259). {@code null} when the senior has no birth date on file —
     *     the prompt builder drops the line rather than failing (CLAUDE.md §8).
     * @param conditions confirmed {@code HEALTH_CONDITION} care records, exact lookup
     *     only (never vector search, CLAUDE.md §8). Empty when health-data consent is
     *     not granted, same gate as the other health-consented fields.
     * @param wakeTime local time, or {@code null} when unknown. Not the same thing as
     *     {@code quietHoursStart} — this is when the senior is normally awake, for the
     *     silence-ladder routine baseline (CLAUDE.md §10); that filter itself is not
     *     built yet (S15P11E102-261), only the value is carried here.
     * @param sleepTime local time, or {@code null} when unknown. See {@code wakeTime}.
     * @param chronicPainArea free-text, senior-reported. {@code null} when unset.
     *     <strong>Never used for emergency triage</strong> — a new complaint must not be
     *     shrugged off as "chronic" (CLAUDE.md §10).
     * @param preferredHospital the clinic or pharmacy the senior actually goes to,
     *     free-text. {@code null} when unset. Distinct from a nearby-clinic search.
     * @param guardianSharingConsentGranted whether the senior has explicitly granted
     *     T3 guardian-sharing consent (S15P11E102-253). The robot must not even
     *     <strong>ask</strong> "may I tell your family?" unless this is {@code true} —
     *     {@code false} covers both an explicit DENIED and the default NOT_REQUESTED,
     *     matching {@code ConversationContextService.isGranted}'s "only explicit
     *     GRANTED passes" rule. This is a permission gate, not content to filter: there
     *     is nothing to omit when consent is missing, so unlike the other
     *     consent-gated fields above, a boolean is exposed directly instead of an
     *     empty collection.
     */
    public record SeniorProfile(
        UUID seniorId,
        String name,
        String preferredName,
        String timeZone,
        String quietHoursStart,
        String quietHoursEnd,
        Map<String, Object> conversationPreferences,
        List<String> avoidTopics,
        Integer age,
        List<String> conditions,
        String wakeTime,
        String sleepTime,
        String chronicPainArea,
        String preferredHospital,
        boolean guardianSharingConsentGranted
    ) {}

    /**
     * Today's aggregates for one senior.
     *
     * <p>Every field is nullable and {@code null} means "not measured", which is not
     * zero. A prompt that turns an unmeasured night into "you did not sleep at all" is
     * worse than one that says nothing about sleep.</p>
     */
    public record TodayState(
        LocalDate date,
        Short medicationTakenCount,
        Short medicationScheduledCount,
        Short mealCount,
        Short waterIntakeCount,
        Integer sleepMinutes,
        Short moodScore,
        Short outingCount
    ) {}

    /** One raw utterance. {@code role} distinguishes SENIOR from ROBOT. */
    public record RawMessage(String role, String content, OffsetDateTime occurredAt) {}

    public record SummaryItem(
        UUID id,
        String summaryType,
        String content,
        OffsetDateTime periodStartedAt,
        OffsetDateTime periodEndedAt
    ) {}

    /**
     * One long-term memory.
     *
     * @param score the combined similarity × importance × recency value that selected it.
     *     Returned so a bad retrieval can be diagnosed without re-running the query.
     * @param lastConfirmedAt lets the prompt date the memory ("what you remember"),
     *     which keeps the robot from stating an old fact as current.
     */
    public record MemoryItem(
        UUID id,
        String memoryType,
        String content,
        List<String> keywords,
        Short importance,
        OffsetDateTime lastConfirmedAt,
        double score
    ) {}

    public record CareRecordItem(
        UUID id,
        String recordType,
        String status,
        Map<String, Object> details
    ) {}

    public record DocumentItem(String title, String content, String sourceRef) {}

    /**
     * Which retrieval paths were actually available.
     *
     * <p>Exists so a caller is never misled by an empty list. "No relevant memory" and
     * "memory search is not wired up" both look like an empty array, but they call for
     * opposite behaviour: the first means say you do not know, the second means the
     * robot should not speak about the past with confidence at all.</p>
     *
     * @param semanticSearch false until the external vector store lands
     *     (S15P11E102-218); memories were then ranked by keyword overlap, importance,
     *     and recency only.
     * @param documentCorpus false until the reference corpus is built.
     * @param notes human-readable reasons, safe to log.
     */
    public record Availability(
        boolean semanticSearch,
        boolean documentCorpus,
        List<String> notes
    ) {}
}
