package com.ssafy.bomi.memory.domain;

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
