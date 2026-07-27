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
 * they are deliberately not physical FKs (§3). Other id columns are raw
 * {@link UUID} logical references, except {@code source_message_id}, which the
 * MVP ERD designates a physical FK to {@code conversation_message} with
 * {@code ON DELETE SET NULL} (§4).</p>
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

    /** Physical FK to {@code conversation_message} ({@code ON DELETE SET NULL}). */
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

    /** Re-clarifies a single missing/ambiguous field (one field at a time — §6). */
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
