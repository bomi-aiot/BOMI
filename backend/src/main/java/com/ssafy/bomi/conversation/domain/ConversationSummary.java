package com.ssafy.bomi.conversation.domain;

import com.ssafy.bomi.embedding.domain.EmbeddingStatus;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.time.OffsetDateTime;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * A conversation-level or daily summary (maps table {@code conversation_summary}).
 *
 * <p>Aggregate root of the summary boundary. The MVP uses {@code CONVERSATION}
 * and {@code DAILY} only, guarded by
 * {@code UNIQUE(senior_id, summary_type, period_started_at, period_ended_at)}.
 * Regeneration creates a new row and links the old one via
 * {@code superseded_by_id} (§4). {@code senior_id} and {@code conversation_id}
 * are raw {@link UUID} logical references.</p>
 *
 * <p>There is no {@code embedding} column, and there will not be one. Upstage
 * embeddings are 4096-dimensional while pgvector indexes at most 2,000
 * ({@code vector}) or 4,000 ({@code halfvec}) dimensions, so semantic search moved
 * to an external vector store (S15P11E102-218). What remains here is the sync
 * bookkeeping that makes that derived index rebuildable.</p>
 */
@Entity
@Table(
    name = "conversation_summary",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_conversation_summary_period",
        columnNames = {"senior_id", "summary_type", "period_started_at", "period_ended_at"}))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ConversationSummary {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "conversation_id")
    private UUID conversationId;

    @Enumerated(EnumType.STRING)
    @Column(name = "summary_type", nullable = false, length = 30)
    private SummaryType summaryType;

    @Column(name = "period_started_at", nullable = false)
    private OffsetDateTime periodStartedAt;

    @Column(name = "period_ended_at", nullable = false)
    private OffsetDateTime periodEndedAt;

    @Column(name = "content", nullable = false, columnDefinition = "text")
    private String content;

    @Column(name = "source_message_count", nullable = false)
    private int sourceMessageCount;

    @Column(name = "generated_at", nullable = false)
    private OffsetDateTime generatedAt;

    @Column(name = "superseded_by_id")
    private UUID supersededById;

    /**
     * Whether this row's vector is present and current in the external vector store.
     *
     * <p>Like {@code memory}, content here is effectively immutable: regeneration
     * writes a new row and supersedes this one, so a synced vector goes stale only
     * on an embedding model change.</p>
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "embedding_status", nullable = false, length = 20)
    private EmbeddingStatus embeddingStatus = EmbeddingStatus.PENDING;

    @Column(name = "embedding_synced_at")
    private OffsetDateTime embeddingSyncedAt;

    /**
     * Which model produced the stored vector. A different model means a different
     * vector space, which silently makes every similarity score meaningless — so it
     * is recorded per row rather than assumed globally.
     */
    @Column(name = "embedding_model", length = 100)
    private String embeddingModel;

    private ConversationSummary(UUID seniorId, UUID conversationId, SummaryType summaryType,
        OffsetDateTime periodStartedAt, OffsetDateTime periodEndedAt, String content,
        int sourceMessageCount) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.conversationId = conversationId;
        this.summaryType = requireNonNull(summaryType, "summaryType");
        this.periodStartedAt = requireNonNull(periodStartedAt, "periodStartedAt");
        this.periodEndedAt = requireNonNull(periodEndedAt, "periodEndedAt");
        this.content = requireText(content, "content");
        this.sourceMessageCount = sourceMessageCount;
        this.generatedAt = OffsetDateTime.now();
    }

    /** Creates a per-conversation summary. */
    public static ConversationSummary forConversation(UUID seniorId, UUID conversationId,
        OffsetDateTime periodStartedAt, OffsetDateTime periodEndedAt, String content,
        int sourceMessageCount) {
        return new ConversationSummary(seniorId, conversationId, SummaryType.CONVERSATION,
            periodStartedAt, periodEndedAt, content, sourceMessageCount);
    }

    /** Creates a daily summary (not tied to a single conversation). */
    public static ConversationSummary forDay(UUID seniorId, OffsetDateTime periodStartedAt,
        OffsetDateTime periodEndedAt, String content, int sourceMessageCount) {
        return new ConversationSummary(seniorId, null, SummaryType.DAILY,
            periodStartedAt, periodEndedAt, content, sourceMessageCount);
    }

    /** Points this (older) summary at the row that regenerated it. */
    public void supersededBy(UUID newerSummaryId) {
        this.supersededById = requireNonNull(newerSummaryId, "newerSummaryId");
    }

    /** Records that this row's vector is now in the external store. */
    public void markEmbeddingSynced(String embeddingModel, OffsetDateTime syncedAt) {
        this.embeddingModel = requireText(embeddingModel, "embeddingModel");
        this.embeddingSyncedAt = requireNonNull(syncedAt, "syncedAt");
        this.embeddingStatus = EmbeddingStatus.SYNCED;
    }

    /**
     * Records that embedding was attempted and failed, kept distinct from
     * {@code PENDING} so a permanently failing row does not look like new work.
     */
    public void markEmbeddingFailed() {
        this.embeddingStatus = EmbeddingStatus.FAILED;
    }

    /** Flags this row for re-embedding, typically after an embedding model change. */
    public void markEmbeddingStale() {
        this.embeddingStatus = EmbeddingStatus.STALE;
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }

    private static <T> T requireNonNull(T value, String field) {
        if (value == null) {
            throw new IllegalArgumentException(field + " must not be null");
        }
        return value;
    }
}
