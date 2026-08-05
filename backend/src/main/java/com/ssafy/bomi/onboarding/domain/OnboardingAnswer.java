package com.ssafy.bomi.onboarding.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * A single normalized onboarding answer (maps table {@code onboarding_answer}).
 *
 * <p>Part of the onboarding aggregate. {@code session_id} references
 * {@code onboarding_session}; {@code respondent_user_id} and
 * {@code confirmed_by_user_id} reference {@code app_user}. The optional
 * {@code source_conversation_id} / {@code source_message_id} link the robot-side
 * evidence (§5); the app channel may have neither. All references are raw
 * {@link UUID} logical references per the raw-UUID convention. That includes
 * {@code source_message_id}; V1~V16 declares no physical FK or automatic delete
 * propagation (§4).</p>
 *
 * <p>{@code answer_value} is the channel-independent normalized answer. It is not
 * a final query source; sensitive intermediate values are not retained
 * indefinitely once materialized.</p>
 */
@Entity
@Table(name = "onboarding_answer")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class OnboardingAnswer {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "session_id", nullable = false)
    private UUID sessionId;

    @Column(name = "question_code", nullable = false, length = 100)
    private String questionCode;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "answer_value")
    private Map<String, Object> answerValue = new HashMap<>();

    @Enumerated(EnumType.STRING)
    @Column(name = "answered_channel", nullable = false, length = 30)
    private OnboardingChannel answeredChannel;

    @Column(name = "respondent_user_id")
    private UUID respondentUserId;

    @Column(name = "source_conversation_id")
    private UUID sourceConversationId;

    /** Logical reference to {@code conversation_message}; deletion is handled by policy. */
    @Column(name = "source_message_id")
    private UUID sourceMessageId;

    @Enumerated(EnumType.STRING)
    @Column(name = "verification_status", nullable = false, length = 30)
    private AnswerVerificationStatus verificationStatus = AnswerVerificationStatus.UNVERIFIED;

    @Column(name = "confirmed_by_user_id")
    private UUID confirmedByUserId;

    @Column(name = "answered_at")
    private OffsetDateTime answeredAt;

    @Column(name = "confirmed_at")
    private OffsetDateTime confirmedAt;

    @Column(name = "updated_at")
    private OffsetDateTime updatedAt;

    private OnboardingAnswer(UUID sessionId, String questionCode, OnboardingChannel answeredChannel,
        UUID respondentUserId, Map<String, Object> answerValue) {
        this.sessionId = requireNonNull(sessionId, "sessionId");
        this.questionCode = requireText(questionCode, "questionCode");
        this.answeredChannel = requireNonNull(answeredChannel, "answeredChannel");
        this.respondentUserId = respondentUserId;
        this.answerValue = answerValue == null ? new HashMap<>() : new HashMap<>(answerValue);
        this.answeredAt = OffsetDateTime.now();
        this.updatedAt = this.answeredAt;
    }

    public static OnboardingAnswer create(UUID sessionId, String questionCode,
        OnboardingChannel answeredChannel, UUID respondentUserId, Map<String, Object> answerValue) {
        return new OnboardingAnswer(sessionId, questionCode, answeredChannel, respondentUserId, answerValue);
    }

    /** Links the robot-side conversation/message evidence for this answer. */
    public void linkEvidence(UUID sourceConversationId, UUID sourceMessageId) {
        this.sourceConversationId = sourceConversationId;
        this.sourceMessageId = sourceMessageId;
        this.updatedAt = OffsetDateTime.now();
    }

    public void updateAnswerValue(Map<String, Object> answerValue) {
        this.answerValue = answerValue == null ? new HashMap<>() : new HashMap<>(answerValue);
        this.updatedAt = OffsetDateTime.now();
    }

    /**
     * Folds newly heard fields into the answer, keeping what was already known.
     *
     * <p><b>Why merging rather than replacing.</b> The contract re-asks one field at a
     * time, so a re-answer is partial by construction. If it replaced the value, a senior
     * who says "혈압약" and then "한 알" would end up with only the dose — the medicine
     * name they gave a moment earlier would be gone, and the flow would ask for it again
     * in an endless circle.</p>
     *
     * <p>This mirrors what {@code RobotClarificationService} already does with a
     * candidate's proposed value. The two paths must accumulate the same way; a robot
     * answering the same contract should not get different behaviour depending on which
     * endpoint it went through.</p>
     *
     * <p>Blank values do not overwrite. An empty string is what arrives when the senior
     * said nothing usable, and letting it erase a known value would turn a misheard turn
     * into data loss.</p>
     */
    public void mergeAnswerValue(Map<String, Object> newFields) {
        if (newFields == null || newFields.isEmpty()) {
            this.updatedAt = OffsetDateTime.now();
            return;
        }
        Map<String, Object> merged = new HashMap<>(this.answerValue);
        newFields.forEach((field, value) -> {
            if (value != null && !value.toString().isBlank()) {
                merged.put(field, value);
            }
        });
        this.answerValue = merged;
        this.updatedAt = OffsetDateTime.now();
    }

    public void confirm(AnswerVerificationStatus verificationStatus, UUID confirmedByUserId) {
        this.verificationStatus = requireNonNull(verificationStatus, "verificationStatus");
        this.confirmedByUserId = confirmedByUserId;
        this.confirmedAt = OffsetDateTime.now();
        this.updatedAt = this.confirmedAt;
    }

    /**
     * Records an answer that is not yet verified, leaving no confirmation trace.
     *
     * <p>Separate from {@link #confirm} because {@code confirmed_at} must stay null: a
     * sensitive value that has not been read back and explicitly agreed to has not been
     * confirmed, and a timestamp saying otherwise is the record that would later be cited
     * as proof the senior agreed to a dose they never heard.</p>
     *
     * <p>Clears any previous confirmation too. Re-answering after a confirmation means
     * the old agreement no longer describes the stored value.</p>
     */
    public void markUnverified() {
        this.verificationStatus = AnswerVerificationStatus.UNVERIFIED;
        this.confirmedByUserId = null;
        this.confirmedAt = null;
        this.updatedAt = OffsetDateTime.now();
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
