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
import org.hibernate.annotations.CreationTimestamp;

/**
 * A single raw utterance within a conversation (maps table
 * {@code conversation_message}).
 *
 * <p>One row is exactly one real utterance. {@code conversation_id} is a raw
 * {@link UUID} logical reference to {@code conversation}. {@code sequence_no} is
 * unique within a conversation; the MVP ERD specifies
 * {@code UNIQUE(conversation_id, sequence_no)} and supporting indexes (§4).
 * {@code occurred_at} is when the utterance happened; {@code created_at} is when
 * the row was stored.</p>
 */
@Entity
@Table(
    name = "conversation_message",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_conversation_message_seq",
        columnNames = {"conversation_id", "sequence_no"}))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ConversationMessage {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "conversation_id", nullable = false)
    private UUID conversationId;

    @Column(name = "sequence_no", nullable = false)
    private int sequenceNo;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false, length = 20)
    private MessageRole role;

    @Column(name = "content", nullable = false, columnDefinition = "text")
    private String content;

    @Column(name = "occurred_at", nullable = false)
    private OffsetDateTime occurredAt;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    private ConversationMessage(UUID conversationId, int sequenceNo, MessageRole role, String content,
        OffsetDateTime occurredAt) {
        this.conversationId = requireNonNull(conversationId, "conversationId");
        this.role = requireNonNull(role, "role");
        this.content = requireText(content, "content");
        this.occurredAt = requireNonNull(occurredAt, "occurredAt");
        if (sequenceNo < 0) {
            throw new IllegalArgumentException("sequenceNo must not be negative");
        }
        this.sequenceNo = sequenceNo;
    }

    public static ConversationMessage of(UUID conversationId, int sequenceNo, MessageRole role,
        String content, OffsetDateTime occurredAt) {
        return new ConversationMessage(conversationId, sequenceNo, role, content, occurredAt);
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
