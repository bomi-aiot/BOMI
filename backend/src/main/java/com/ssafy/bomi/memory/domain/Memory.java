package com.ssafy.bomi.memory.domain;

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
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * A long-term personalization fact (maps table {@code memory}).
 *
 * <p>Aggregate root. {@code content} is one long-term fact understandable without
 * the conversation; raw/summary text is never copied in. Retrieval mixes exact
 * {@code keywords} matching with semantic {@code embedding} search after
 * pre-filtering on senior, {@code lifecycle_status=ACTIVE},
 * {@code verification_status != REJECTED} and allowed visibility (§4). A change
 * is expressed as a new memory plus {@code superseded_by_id};
 * {@code source_candidate_id} is unique to prevent duplicate materialization.</p>
 *
 * <p>All references ({@code senior_id}, {@code source_conversation_id},
 * {@code source_summary_id}, {@code source_candidate_id}, {@code superseded_by_id})
 * are raw {@link UUID} logical references. The {@code embedding} ({@code VECTOR})
 * column is intentionally not mapped: model/dimension and the vector index are
 * TBD (§12) pending a pgvector integration decision.</p>
 */
@Entity
@Table(
    name = "memory",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_memory_source_candidate",
        columnNames = "source_candidate_id"))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Memory {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "source_conversation_id")
    private UUID sourceConversationId;

    @Column(name = "source_summary_id")
    private UUID sourceSummaryId;

    @Column(name = "source_candidate_id")
    private UUID sourceCandidateId;

    @Column(name = "superseded_by_id")
    private UUID supersededById;

    @Enumerated(EnumType.STRING)
    @Column(name = "memory_type", nullable = false, length = 50)
    private MemoryType memoryType;

    @Column(name = "content", nullable = false, columnDefinition = "text")
    private String content;

    @Enumerated(EnumType.STRING)
    @Column(name = "verification_status", nullable = false, length = 30)
    private MemoryVerificationStatus verificationStatus = MemoryVerificationStatus.UNVERIFIED;

    @Enumerated(EnumType.STRING)
    @Column(name = "lifecycle_status", nullable = false, length = 30)
    private MemoryLifecycleStatus lifecycleStatus = MemoryLifecycleStatus.ACTIVE;

    @Enumerated(EnumType.STRING)
    @Column(name = "visibility", nullable = false, length = 30)
    private MemoryVisibility visibility = MemoryVisibility.PRIVATE;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "keywords")
    private List<String> keywords = new ArrayList<>();

    @Column(name = "importance")
    private Short importance;

    @Column(name = "first_observed_at")
    private OffsetDateTime firstObservedAt;

    @Column(name = "last_confirmed_at")
    private OffsetDateTime lastConfirmedAt;

    @Column(name = "last_used_at")
    private OffsetDateTime lastUsedAt;

    /**
     * Whether this row's vector is present and current in the external vector store.
     *
     * <p>The vector itself is not stored here. Upstage embeddings are
     * 4096-dimensional and pgvector cannot index beyond 2,000 ({@code vector}) or
     * 4,000 ({@code halfvec}) dimensions, so semantic search moved to an external
     * store (S15P11E102-218). That store is a derived index and this column is how
     * we know what to rebuild when it is lost.</p>
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "embedding_status", nullable = false, length = 20)
    private EmbeddingStatus embeddingStatus = EmbeddingStatus.PENDING;

    @Column(name = "embedding_synced_at")
    private OffsetDateTime embeddingSyncedAt;

    /**
     * Which model produced the stored vector.
     *
     * <p>Change the model and every existing vector is worthless: a different model
     * is a different vector space, so the similarity numbers stop meaning anything.
     * That failure throws no exception and shows up only as quietly worse recall,
     * which is why the model is recorded per row.</p>
     */
    @Column(name = "embedding_model", length = 100)
    private String embeddingModel;

    private Memory(UUID seniorId, MemoryType memoryType, String content, MemoryVisibility visibility) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.memoryType = requireNonNull(memoryType, "memoryType");
        this.content = requireText(content, "content");
        this.visibility = requireNonNull(visibility, "visibility");
        this.firstObservedAt = OffsetDateTime.now();
    }

    public static Memory create(UUID seniorId, MemoryType memoryType, String content) {
        return new Memory(seniorId, memoryType, content, MemoryVisibility.PRIVATE);
    }

    public static Memory create(UUID seniorId, MemoryType memoryType, String content,
        MemoryVisibility visibility) {
        return new Memory(seniorId, memoryType, content, visibility);
    }

    /** Records the provenance of this memory (any of the sources may be null). */
    public void attachSources(UUID sourceConversationId, UUID sourceSummaryId, UUID sourceCandidateId) {
        this.sourceConversationId = sourceConversationId;
        this.sourceSummaryId = sourceSummaryId;
        this.sourceCandidateId = sourceCandidateId;
    }

    public void updateKeywords(List<String> keywords) {
        this.keywords = keywords == null ? new ArrayList<>() : new ArrayList<>(keywords);
    }

    public void setImportance(Short importance) {
        if (importance != null && (importance < 1 || importance > 5)) {
            throw new IllegalArgumentException("importance must be between 1 and 5");
        }
        this.importance = importance;
    }

    public void changeVisibility(MemoryVisibility visibility) {
        this.visibility = requireNonNull(visibility, "visibility");
    }

    public void changeVerificationStatus(MemoryVerificationStatus status) {
        this.verificationStatus = requireNonNull(status, "verificationStatus");
        this.lastConfirmedAt = OffsetDateTime.now();
    }

    public void changeLifecycleStatus(MemoryLifecycleStatus status) {
        this.lifecycleStatus = requireNonNull(status, "lifecycleStatus");
    }

    /** Points this (older) memory at the row that superseded it. */
    public void supersededBy(UUID newerMemoryId) {
        this.supersededById = requireNonNull(newerMemoryId, "newerMemoryId");
        this.lifecycleStatus = MemoryLifecycleStatus.SUPERSEDED;
    }

    public void markUsed() {
        this.lastUsedAt = OffsetDateTime.now();
    }

    /**
     * Records that this row's vector is now in the external store.
     *
     * <p>{@code content} is immutable once created — a changed fact becomes a new
     * memory linked by {@code superseded_by_id} (§4) — so a synced vector can only
     * go stale by a model change, never by an edit.</p>
     */
    public void markEmbeddingSynced(String embeddingModel, OffsetDateTime syncedAt) {
        this.embeddingModel = requireText(embeddingModel, "embeddingModel");
        this.embeddingSyncedAt = requireNonNull(syncedAt, "syncedAt");
        this.embeddingStatus = EmbeddingStatus.SYNCED;
    }

    /**
     * Records that embedding was attempted and failed. Kept distinct from
     * {@code PENDING} so a permanently failing row stays visible instead of looking
     * like fresh work forever.
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
