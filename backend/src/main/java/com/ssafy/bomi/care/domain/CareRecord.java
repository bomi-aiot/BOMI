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
 * once frozen. All id columns are raw {@link UUID} logical references, including
 * {@code source_message_id}; V1~V16 declares no physical FK or automatic delete
 * propagation (§4).</p>
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

    /**
     * Logical reference to {@code conversation_message}; deletion is handled by policy.
     *
     * <p>그 "policy" 는 {@code ConversationRawPurgeService} 다 — 물리 FK 도
     * {@code ON DELETE SET NULL} 도 없으므로(V1 주석) 발화가 지워질 때 이 값을 비우는
     * 것은 오로지 그 배치의 책임이다.</p>
     */
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
     * Where this record sits on the timeline (S15P11E102-230).
     *
     * <p>When it happened for an event, when it is due for a scheduled one. One axis,
     * so a range query means the same thing for every record type. Before this column
     * existed the time lived under four different keys inside {@link #details}
     * ({@code scheduledAt}, {@code startsAt}, {@code ts}, {@code metricDate}), which
     * meant a trend query had to load every one of a senior's records and parse JSON
     * in Java.</p>
     *
     * <p><b>Null is meaningful and stays null.</b> Two different reasons: the record has
     * no single point in time (a recurring {@code MEDICATION_SCHEDULE}, a
     * {@code MEDICATION} prescription), or we genuinely do not know. Filling it in with
     * the current time would put an old alert at the top of the guardian's screen — the
     * same "unknown is not zero" rule V4 is built on.</p>
     */
    @Column(name = "occurred_at")
    private OffsetDateTime occurredAt;

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
        this.occurredAt = CareRecordTime.fromDetails(this.details);
    }

    /**
     * Creates a record, taking {@link #occurredAt} from {@code details} when it is there.
     *
     * <p><b>Why the factory reads the JSON.</b> S15P11E102-230 exists because the time of a
     * care record lived under four different keys inside {@code details} and nothing forced
     * a write path to use any of them. A new writer could omit the key, compile, save, and
     * only vanish from the aggregate — the guardian then sees a missed dose that was never
     * missed. Deriving here inverts that: a writer that puts a time in {@code details}
     * cannot lose it, whatever it forgets to call.</p>
     *
     * <p>Callers whose time is <em>not</em> in {@code details} — an observation that is
     * happening right now, an alert that carries its own clock — still call
     * {@link #occurredAt} afterwards, and that wins. Which keys are read, and in what order,
     * lives in {@link CareRecordTime}; it mirrors the {@code COALESCE} in V7 so backfilled
     * rows and new rows land on the same clock.</p>
     */
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

    /**
     * 보존기간이 지난 근거 발화의 링크를 끊는다 (ERD §4, 검증 시나리오 31).
     *
     * <p><b>유일한 호출자는 {@code ConversationRawPurgeService} 다.</b> care_record 는
     * 최종 조회원(§1)이라 이 행 자체는 절대 지우지 않는다 — 지우는 것은 "어느 발화에서
     * 나왔나"라는 끈 하나뿐이고, 확정된 내용({@link #details})은 그대로 남는다.</p>
     *
     * <p>{@link #attachSources} 로 대신할 수 없어서 따로 만든다: 그 메서드는 5개 필드를
     * 한꺼번에 덮어써서 발화 하나만 비우려면 {@code scenarioId}·
     * {@code sourceConversationId}·{@code sourceCandidateId}·{@code createdByUserId}
     * 를 전부 되먹여야 한다. 그중 {@code sourceCandidateId} 는 유니크 제약
     * ({@code uq_care_record_source_candidate})이 걸린 중복 실체화 방지 장치라, 한 번만
     * 빠뜨리면 같은 후보가 두 번 반영될 수 있는 상태로 되돌아간다.</p>
     */
    public void clearSourceMessage() {
        this.sourceMessageId = null;
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

    /**
     * Places this record on the timeline (S15P11E102-230).
     *
     * <p>Every write path calls this. Passing null is allowed and means one of the two
     * things described on {@link #occurredAt} — it is not a "forgot to set it" escape
     * hatch, and a caller that cannot work out a time should say so in a comment.</p>
     */
    public void occurredAt(OffsetDateTime occurredAt) {
        this.occurredAt = occurredAt;
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
     * Links this record to a parent record (e.g. a MEDICATION_SCHEDULE under its
     * MEDICATION). Distinct from {@link #supersedeWith}: no status change, used when a
     * child is created together with its parent (S15P11E102-224).
     */
    public void assignParent(UUID parentRecordId) {
        this.parentRecordId = requireNonNull(parentRecordId, "parentRecordId");
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
