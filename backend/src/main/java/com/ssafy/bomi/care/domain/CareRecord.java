package com.ssafy.bomi.care.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

/**
 * A confirmed care record — health/medication/schedule/observation/notification
 * (maps table {@code care_record}).
 *
 * <p>Aggregate root and one of the final query sources (§1). A confirmed value is
 * never mutated in place: a change creates a new row linked by
 * {@code parent_record_id}, and the previous row becomes {@code SUPERSEDED} (§8).
 * {@code source_candidate_id} is unique so the same candidate cannot be
 * materialized twice.</p>
 *
 * <p>{@code record_type} is kept as a raw {@link String} because the allowed set
 * ({@code CARE_RECORD_ENUM}) is broad and still evolving; it can become an enum
 * once frozen. All id columns are raw {@link UUID} logical references, except
 * {@code source_message_id}, which the MVP ERD designates a physical FK to
 * {@code conversation_message} with {@code ON DELETE SET NULL} (§4).</p>
 */
@Entity
@Table(
    name = "care_record",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_care_record_source_candidate",
        columnNames = "source_candidate_id"))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CareRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "senior_id", nullable = false)
    private UUID seniorId;

    @Column(name = "parent_record_id")
    private UUID parentRecordId;

    @Column(name = "scenario_id")
    private UUID scenarioId;

    @Column(name = "source_conversation_id")
    private UUID sourceConversationId;

    /** Physical FK to {@code conversation_message} ({@code ON DELETE SET NULL}). */
    @Column(name = "source_message_id")
    private UUID sourceMessageId;

    @Column(name = "recipient_guardian_id")
    private UUID recipientGuardianId;

    @Column(name = "created_by_user_id")
    private UUID createdByUserId;

    @Column(name = "source_candidate_id")
    private UUID sourceCandidateId;

    @Column(name = "record_type", nullable = false, length = 50)
    private String recordType;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 30)
    private CareRecordStatus status = CareRecordStatus.ACTIVE;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "details", nullable = false)
    private Map<String, Object> details = new HashMap<>();

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "recurrence")
    private Map<String, Object> recurrence;

    /**
     * How urgently the guardian hears about this, for notification-type records.
     *
     * <p>Null on every record that is not an outbound notification — most rows are
     * medication schedules and observations, which nobody is paged about.</p>
     *
     * <p>A column rather than a key inside {@link #details} because "is there an
     * unsent T1?" is a safety query, and pulling it out of JSON on every scan is
     * the wrong place to spend that time.</p>
     */
    @Enumerated(EnumType.STRING)
    @Column(name = "notification_tier", length = 10)
    private NotificationTier notificationTier;

    private CareRecord(UUID seniorId, String recordType, Map<String, Object> details) {
        this.seniorId = requireNonNull(seniorId, "seniorId");
        this.recordType = requireText(recordType, "recordType");
        this.details = details == null ? new HashMap<>() : new HashMap<>(details);
    }

    public static CareRecord create(UUID seniorId, String recordType, Map<String, Object> details) {
        return new CareRecord(seniorId, recordType, details);
    }

    /** Records the provenance of a materialized care record (any source may be null). */
    public void attachSources(UUID scenarioId, UUID sourceConversationId, UUID sourceMessageId,
        UUID sourceCandidateId, UUID createdByUserId) {
        this.scenarioId = scenarioId;
        this.sourceConversationId = sourceConversationId;
        this.sourceMessageId = sourceMessageId;
        this.sourceCandidateId = sourceCandidateId;
        this.createdByUserId = createdByUserId;
    }

    public void assignRecipientGuardian(UUID recipientGuardianId) {
        this.recipientGuardianId = recipientGuardianId;
    }

    /**
     * Marks this record as an outbound guardian notification at the given tier.
     *
     * <p>There is no T4: T4 means never sent, so no notification record exists for
     * it. It is expressed as {@code memory.visibility = PRIVATE} instead.</p>
     *
     * <p>Setting the tier does not authorize sending. T2 and T3 must still check
     * {@code guardian_sharing_consent_status}; only T1 proceeds regardless, because
     * it is life safety (CLAUDE.md §9).</p>
     */
    public void markAsNotification(NotificationTier tier, UUID recipientGuardianId) {
        this.notificationTier = requireNonNull(tier, "tier");
        this.recipientGuardianId = recipientGuardianId;
    }

    public void updateDetails(Map<String, Object> details) {
        this.details = details == null ? new HashMap<>() : new HashMap<>(details);
    }

    public void updateRecurrence(Map<String, Object> recurrence) {
        this.recurrence = recurrence == null ? null : new HashMap<>(recurrence);
    }

    public void changeStatus(CareRecordStatus status) {
        this.status = requireNonNull(status, "status");
    }

    /**
     * Creates the successor row for a value change, linking back to this record and
     * marking this one {@code SUPERSEDED} (§8).
     */
    public CareRecord supersedeWith(String recordType, Map<String, Object> details) {
        CareRecord next = new CareRecord(this.seniorId, recordType, details);
        next.parentRecordId = this.id;
        this.status = CareRecordStatus.SUPERSEDED;
        return next;
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
