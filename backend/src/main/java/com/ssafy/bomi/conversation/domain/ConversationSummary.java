package com.ssafy.bomi.conversation.domain;

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
 * <p>The {@code embedding} ({@code VECTOR}) column is intentionally not mapped
 * here: the model and dimension, plus the vector index, are still TBD (§12) and
 * require a pgvector integration decision before it becomes a managed column.</p>
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
