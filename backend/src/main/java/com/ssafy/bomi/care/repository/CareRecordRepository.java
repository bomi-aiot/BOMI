package com.ssafy.bomi.care.repository;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CareRecordRepository extends JpaRepository<CareRecord, UUID> {

    // 가디언 대시보드용 조회 (S15P11E102-221).
    List<CareRecord> findBySeniorId(UUID seniorId);

    // 복약 자식 스케줄 조회 (S15P11E102-224).
    List<CareRecord> findByParentRecordId(UUID parentRecordId);

    // 복약 알림 스케줄러의 폴링 대상: 전 어르신의 ACTIVE 복약 스케줄 (시나리오 ②).
    List<CareRecord> findByRecordTypeAndStatus(String recordType, CareRecordStatus status);

    List<CareRecord> findBySeniorIdAndStatus(UUID seniorId, CareRecordStatus status);

    List<CareRecord> findBySeniorIdAndRecordTypeAndStatus(
            UUID seniorId, String recordType, CareRecordStatus status);

    /**
     * Active care records of the given types for one senior.
     *
     * <p>Restricted to {@code ACTIVE} because a superseded medication row is a dose that
     * changed. Handing both to a prompt is how a robot ends up describing an old
     * schedule as the current one, and medication is exactly where that must not happen.</p>
     *
     * <p>Callers pass the record types they need. Which types are permitted depends on
     * the senior's consent for that category, and that check belongs in the assembly
     * service — a repository cannot see consent.</p>
     */
    List<CareRecord> findBySeniorIdAndStatusAndRecordTypeIn(
        UUID seniorId, CareRecordStatus status, Collection<String> recordTypes);

    /**
     * How many records of one type fall inside a time window (S15P11E102-230).
     *
     * <p>This replaces "load every record this senior has ever had, then parse
     * {@code details} in Java". That worked while the table was small and got worse
     * every day the daily batch ran. The index
     * {@code (senior_id, record_type, occurred_at)} is laid out for exactly this.</p>
     *
     * <p>The window is half-open ({@code >= from, < to}) so consecutive days never
     * double-count the midnight boundary — same rule as
     * {@code ConversationMessageRepository.findForSeniorBetween}.</p>
     *
     * <p>Rows with a null {@code occurred_at} are excluded by the comparison itself.
     * That is intended: a dose we cannot place in time must not be attributed to a day.
     * Counting it into today would show the guardian adherence the senior never had.</p>
     */
    @Query("""
        SELECT count(r) FROM CareRecord r
        WHERE r.seniorId = :seniorId
          AND r.recordType = :recordType
          AND r.occurredAt >= :from AND r.occurredAt < :to
        """)
    long countByTypeBetween(
        @Param("seniorId") UUID seniorId,
        @Param("recordType") String recordType,
        @Param("from") OffsetDateTime from,
        @Param("to") OffsetDateTime to);

    /**
     * Active records of the given types inside a time window (S15P11E102-230).
     *
     * <p>Used by the door greeting: "is there an appointment today", "was any dose
     * already taken today". {@code ACTIVE} only, for the same reason as
     * {@link #findBySeniorIdAndStatusAndRecordTypeIn} — a cancelled appointment is not
     * something to remind anyone about.</p>
     */
    @Query("""
        SELECT r FROM CareRecord r
        WHERE r.seniorId = :seniorId
          AND r.status = :status
          AND r.recordType IN :recordTypes
          AND r.occurredAt >= :from AND r.occurredAt < :to
        """)
    List<CareRecord> findByTypesBetween(
        @Param("seniorId") UUID seniorId,
        @Param("status") CareRecordStatus status,
        @Param("recordTypes") Collection<String> recordTypes,
        @Param("from") OffsetDateTime from,
        @Param("to") OffsetDateTime to);
}
