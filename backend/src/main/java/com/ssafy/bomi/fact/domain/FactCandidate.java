package com.ssafy.bomi.fact.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

/**
 * An unconfirmed fact under clarification/confirmation/coordination (maps table
 * {@code fact_candidate}).
 *
 * <p>Aggregate root of the candidate boundary. {@code status} is the processing
 * stage; {@code coordination_status} is the separate PRIMARY-coordination stage —
 * the two are never conflated (§6). Only {@code confirmed_value} may be
 * materialized into a final source.</p>
 *
 * <p>{@code target_entity_id} and {@code materialized_target_id} are
 * <b>logical</b> references whose target table depends on {@code target_domain};
 * they are deliberately not physical FKs (§3). All other id columns, including
 * {@code source_message_id}, are also raw {@link UUID} logical references. V1~V16
 * declares no physical FK or automatic delete propagation (§4).</p>
 */
@Entity
@Table(name = "fact_candidate")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class FactCandidate {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Enumerated(EnumType.STRING)
    @Column(name = "source_type", nullable = false, length = 40)
    private FactSourceType sourceType;

    @Column(name = "onboarding_answer_id")
    private UUID onboardingAnswerId;

    @Column(name = "conversation_id")
    private UUID conversationId;

    /** Logical reference to {@code conversation_message}; deletion is handled by policy. */
    @Column(name = "source_message_id")
    private UUID sourceMessageId;

    @Enumerated(EnumType.STRING)
    @Column(name = "target_domain", nullable = false, length = 40)
    private FactTargetDomain targetDomain;

    @Column(name = "fact_type", nullable = false, length = 80)
    private String factType;

    @Enumerated(EnumType.STRING)
    @Column(name = "operation", nullable = false, length = 20)
    private FactOperation operation;

    /** Logical reference whose target table depends on {@code targetDomain} (not a physical FK). */
    @Column(name = "target_entity_id")
    private UUID targetEntityId;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "proposed_value", nullable = false)
    private Map<String, Object> proposedValue = new HashMap<>();

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "confirmed_value")
    private Map<String, Object> confirmedValue;

    @JdbcTypeCode(SqlTypes.ARRAY)
    @Column(name = "missing_fields", nullable = false)
    private List<String> missingFields = new ArrayList<>();

    @Enumerated(EnumType.STRING)
    @Column(name = "risk_level", nullable = false, length = 20)
    private RiskLevel riskLevel;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 40)
    private FactCandidateStatus status = FactCandidateStatus.CAPTURED;

    @Enumerated(EnumType.STRING)
    @Column(name = "clarification_reason", length = 60)
    private ClarificationReason clarificationReason;

    @Column(name = "clarification_count", nullable = false)
    private int clarificationCount = 0;

    @Column(name = "initiated_by_user_id")
    private UUID initiatedByUserId;

    @Column(name = "confirmed_by_user_id")
    private UUID confirmedByUserId;

    @Column(name = "requires_coordination", nullable = false)
    private boolean requiresCoordination = false;

    @Enumerated(EnumType.STRING)
    @Column(name = "coordination_status", nullable = false, length = 50)
    private CoordinationStatus coordinationStatus = CoordinationStatus.NOT_REQUIRED;

    @Enumerated(EnumType.STRING)
    @Column(name = "senior_position", nullable = false, length = 30)
    private SeniorPosition seniorPosition = SeniorPosition.NOT_REQUESTED;

    @Enumerated(EnumType.STRING)
    @Column(name = "primary_guardian_decision", nullable = false, length = 50)
    private PrimaryGuardianDecision primaryGuardianDecision = PrimaryGuardianDecision.PENDING;

    @Column(name = "primary_guardian_id")
    private UUID primaryGuardianId;

    @Column(name = "contact_attempt_count", nullable = false)
    private int contactAttemptCount = 0;

    @Column(name = "last_contact_attempted_at")
    private OffsetDateTime lastContactAttemptedAt;

    @Enumerated(EnumType.STRING)
    @Column(name = "unreachable_reason", length = 50)
    private UnreachableReason unreachableReason;

    @Column(name = "coordination_deadline_at")
    private OffsetDateTime coordinationDeadlineAt;

    @Column(name = "coordination_completed_at")
    private OffsetDateTime coordinationCompletedAt;

    @Column(name = "coordination_note", columnDefinition = "text")
    private String coordinationNote;

    /** Logical reference to the materialized target row (not a physical FK). */
    @Column(name = "materialized_target_id")
    private UUID materializedTargetId;

    @Column(name = "materialized_at")
    private OffsetDateTime materializedAt;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    @Column(name = "confirmed_at")
    private OffsetDateTime confirmedAt;

    @Column(name = "expires_at")
    private OffsetDateTime expiresAt;

    private FactCandidate(FactSourceType sourceType, UUID seniorId, FactTargetDomain targetDomain,
        String factType, FactOperation operation, Map<String, Object> proposedValue, RiskLevel riskLevel) {
        this.sourceType = requireNonNull(sourceType, "sourceType");
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.targetDomain = requireNonNull(targetDomain, "targetDomain");
        this.factType = requireText(factType, "factType");
        this.operation = requireNonNull(operation, "operation");
        this.proposedValue = proposedValue == null ? new HashMap<>() : new HashMap<>(proposedValue);
        this.riskLevel = requireNonNull(riskLevel, "riskLevel");
    }

    /** Captures a candidate proposed from an onboarding answer ({@code onboardingAnswerId} required). */
    public static FactCandidate fromOnboardingAnswer(UUID seniorId, UUID onboardingAnswerId,
        FactTargetDomain targetDomain, String factType, FactOperation operation,
        Map<String, Object> proposedValue, RiskLevel riskLevel) {
        FactCandidate c = new FactCandidate(FactSourceType.ONBOARDING_ANSWER, seniorId, targetDomain,
            factType, operation, proposedValue, riskLevel);
        c.onboardingAnswerId = requireNonNull(onboardingAnswerId, "onboardingAnswerId");
        return c;
    }

    /** Captures a candidate evidenced by a conversation message (both ids required). */
    public static FactCandidate fromConversationMessage(UUID seniorId, UUID conversationId,
        UUID sourceMessageId, FactTargetDomain targetDomain, String factType, FactOperation operation,
        Map<String, Object> proposedValue, RiskLevel riskLevel) {
        FactCandidate c = new FactCandidate(FactSourceType.CONVERSATION_MESSAGE, seniorId, targetDomain,
            factType, operation, proposedValue, riskLevel);
        c.conversationId = requireNonNull(conversationId, "conversationId");
        c.sourceMessageId = requireNonNull(sourceMessageId, "sourceMessageId");
        return c;
    }

    /**
     * Replaces the proposed value after a re-answer.
     *
     * <p>Used when an onboarding answer is upserted: the candidate is updated in place
     * rather than duplicated, so the senior is never asked about the same fact twice —
     * once from the stale candidate and once from the new one.</p>
     *
     * <p>Deliberately does not touch {@code confirmedValue}. Only a confirmation may
     * set that, and a new proposal must not quietly inherit an old confirmation.</p>
     */
    public void updateProposedValue(Map<String, Object> proposedValue) {
        this.proposedValue = proposedValue == null ? new HashMap<>() : new HashMap<>(proposedValue);
    }

    /**
     * Links the conversation evidence for a value supplied by voice.
     *
     * <p>An onboarding-sourced candidate can still be clarified in ordinary conversation
     * later. Recording where the value came from is what makes "why does the record say
     * this?" answerable afterwards.</p>
     *
     * <p>Null-safe on purpose: the app channel has no conversation, and refusing to
     * record an answer because it lacks a transcript would block the app entirely.</p>
     */
    public void recordEvidence(UUID conversationId, UUID sourceMessageId) {
        if (conversationId != null) {
            this.conversationId = conversationId;
        }
        if (sourceMessageId != null) {
            this.sourceMessageId = sourceMessageId;
        }
    }

    /**
     * Re-clarifies the fields that are still missing or ambiguous.
     *
     * <p>Stores <b>all</b> of them. Asking about one at a time is a dialogue rule, not a
     * storage rule (MVP ERD §6) — if only the asked field were stored, filling it would
     * make the candidate look complete while two fields were still empty, and a
     * half-known medication would be confirmed.</p>
     */
    public void needsClarification(ClarificationReason reason, List<String> missingFields) {
        this.status = FactCandidateStatus.NEEDS_CLARIFICATION;
        this.clarificationReason = requireNonNull(reason, "reason");
        this.missingFields = missingFields == null ? new ArrayList<>() : new ArrayList<>(missingFields);
        this.clarificationCount++;
    }

    public void needsConfirmation() {
        this.status = FactCandidateStatus.NEEDS_CONFIRMATION;
    }

    /** Records the confirmed final value; only this value may later be materialized (§6). */
    public void confirm(Map<String, Object> confirmedValue, UUID confirmedByUserId) {
        this.confirmedValue = confirmedValue == null ? new HashMap<>() : new HashMap<>(confirmedValue);
        this.confirmedByUserId = confirmedByUserId;
        this.status = FactCandidateStatus.CONFIRMED;
        this.confirmedAt = OffsetDateTime.now();
    }

    /** Opens the PRIMARY-coordination flow for a conflicting sensitive value (§7). */
    public void requireCoordination(UUID primaryGuardianId, OffsetDateTime deadlineAt) {
        this.requiresCoordination = true;
        this.status = FactCandidateStatus.COORDINATION_REQUIRED;
        this.coordinationStatus = CoordinationStatus.COORDINATION_REQUIRED;
        this.primaryGuardianId = primaryGuardianId;
        this.coordinationDeadlineAt = deadlineAt;
    }

    public void recordSeniorPosition(SeniorPosition position) {
        this.seniorPosition = requireNonNull(position, "position");
    }

    public void recordPrimaryDecision(PrimaryGuardianDecision decision) {
        this.primaryGuardianDecision = requireNonNull(decision, "decision");
    }

    public void updateCoordinationStatus(CoordinationStatus coordinationStatus) {
        this.coordinationStatus = requireNonNull(coordinationStatus, "coordinationStatus");
        if (coordinationStatus == CoordinationStatus.COMPLETED) {
            this.coordinationCompletedAt = OffsetDateTime.now();
        }
    }

    /** Logs a contact attempt to the senior during coordination (§7). */
    public void recordContactAttempt() {
        this.contactAttemptCount++;
        this.lastContactAttemptedAt = OffsetDateTime.now();
    }

    public void markUnreachable(UnreachableReason reason) {
        this.unreachableReason = requireNonNull(reason, "reason");
        this.seniorPosition = SeniorPosition.UNREACHABLE;
        this.coordinationStatus = CoordinationStatus.SENIOR_UNREACHABLE;
    }

    public void setCoordinationNote(String note) {
        this.coordinationNote = note;
    }

    /** Marks the confirmed value as reflected into its final target row (§6). */
    public void materialize(UUID materializedTargetId) {
        if (this.status != FactCandidateStatus.CONFIRMED) {
            throw new IllegalStateException("only a CONFIRMED candidate can be materialized");
        }
        this.materializedTargetId = requireNonNull(materializedTargetId, "materializedTargetId");
        this.status = FactCandidateStatus.MATERIALIZED;
        this.materializedAt = OffsetDateTime.now();
    }

    public void reject() {
        this.status = FactCandidateStatus.REJECTED;
    }

    /**
     * 어르신 본인의 요청("기억하지 마")으로 후보를 닫는다 (S15P11E102-348).
     *
     * <p>미확정 단계({@link #isCancellableBySenior()})에서만 허용한다.
     * {@code CONFIRMED}/{@code MATERIALIZED} 는 이미 사실로 반영됐거나 반영 직전이라
     * 이 경로로 지우면 "지웠다"는 약속과 실제가 어긋난다 — 그쪽 되돌리기는 보호자
     * 화면의 몫으로 남긴다(티켓 미결 사항). 시각은 {@code updated_at}
     * (@UpdateTimestamp)이 자동으로 남는다.</p>
     */
    public void cancelBySenior() {
        if (!isCancellableBySenior()) {
            throw new IllegalStateException(
                "only an unconfirmed candidate can be cancelled by the senior (status="
                    + this.status + ")");
        }
        this.status = FactCandidateStatus.CANCELLED_BY_SENIOR;
    }

    /** 어르신 요청 취소가 허용되는 미확정 단계인가. 서비스의 대상 선별과 같은 기준이다. */
    public boolean isCancellableBySenior() {
        return this.status == FactCandidateStatus.CAPTURED
            || this.status == FactCandidateStatus.NEEDS_CLARIFICATION
            || this.status == FactCandidateStatus.NEEDS_CONFIRMATION
            || this.status == FactCandidateStatus.COORDINATION_REQUIRED;
    }

    public void expire(OffsetDateTime expiresAt) {
        this.status = FactCandidateStatus.EXPIRED;
        this.expiresAt = expiresAt;
    }

    public void initiatedBy(UUID userId) {
        this.initiatedByUserId = userId;
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
