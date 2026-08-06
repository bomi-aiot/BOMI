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

    /**
     * Why this utterance happened. {@link #role} says who spoke; this says what
     * made them speak.
     *
     * <p>Nullable because rows written before this column existed have genuinely
     * unknown provenance, and labelling them all {@code USER} would misclassify the
     * robot's own rows. Every new write sets it — prefer
     * {@link #proactive} / {@link #reactive} over the bare factory.</p>
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "trigger_type", length = 30)
    private MessageTriggerType triggerType;

    /**
     * Priority the proactive gate granted this utterance, or null.
     *
     * <p>Null for every reactive turn: answering a senior who just spoke needs no
     * permission, so it never reaches the gate (CLAUDE.md §7).</p>
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "priority", length = 20)
    private MessagePriority priority;

    /**
     * Whether this senior utterance was an orientation question ("what day is it?").
     *
     * <p>Counted into the T2 trend and <b>nowhere else</b>. Rising repetition is an
     * early cognitive-decline signal, but it must never reach the prompt: a model told
     * "asked 9 times already" lets that leak into its tone, and the tenth answer stops
     * sounding as warm as the first. Splitting the two destinations is what makes both
     * behaviours possible at once (CLAUDE.md §8).</p>
     *
     * <p>Nullable, and null is not false. Rows written before this column existed, and
     * rows from channels that do not classify, genuinely do not know.</p>
     */
    @Column(name = "orientation_question")
    private Boolean orientationQuestion;

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

    /**
     * A turn the senior started, or the robot answering one. Carries no priority
     * because it never went through the gate.
     */
    public static ConversationMessage reactive(UUID conversationId, int sequenceNo, MessageRole role,
        String content, OffsetDateTime occurredAt) {
        ConversationMessage message =
            new ConversationMessage(conversationId, sequenceNo, role, content, occurredAt);
        message.triggerType = MessageTriggerType.USER;
        return message;
    }

    /**
     * Attaches why this utterance happened, after the row was built.
     *
     * <p>The {@link #reactive} / {@link #proactive} factories cover the two shapes the
     * conversation domain creates itself. This exists for the robot ingestion path, where
     * the trigger arrives as data rather than as a choice of factory — the robot already
     * decided, and re-deriving it from the text here would put the same judgement in two
     * places.</p>
     *
     * <p>Priority stays null for reactive turns. Answering someone who just spoke never
     * reaches the gate, so recording a priority would invent a decision nobody made.</p>
     */
    public void attachProvenance(MessageTriggerType triggerType, MessagePriority priority) {
        this.triggerType = requireNonNull(triggerType, "triggerType");
        this.priority = priority;
    }

    /**
     * Marks a senior utterance as an orientation question.
     *
     * <p>The robot decides this — it already classified the turn. Re-analysing the text
     * on the server would put the same judgement in two places, and a server that starts
     * analysing conversation content soon does it for other purposes too.</p>
     */
    public void markOrientationQuestion(boolean orientationQuestion) {
        this.orientationQuestion = orientationQuestion;
    }

    /**
     * A robot utterance the gate allowed through.
     *
     * <p>Recording both why and at what priority is what later answers "why did the
     * robot speak at 3 a.m.", separates robot from senior volume in the T2 metrics,
     * and lets us retrieve recent phrasings so wording varies (CLAUDE.md §17.8).</p>
     */
    public static ConversationMessage proactive(UUID conversationId, int sequenceNo, String content,
        OffsetDateTime occurredAt, MessageTriggerType triggerType, MessagePriority priority) {
        ConversationMessage message = new ConversationMessage(conversationId, sequenceNo,
            MessageRole.ROBOT, content, occurredAt);
        message.triggerType = requireNonNull(triggerType, "triggerType");
        message.priority = requireNonNull(priority, "priority");
        return message;
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
