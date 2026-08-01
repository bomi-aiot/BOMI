package com.ssafy.bomi.care.repository;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import java.util.Collection;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CareRecordRepository extends JpaRepository<CareRecord, UUID> {

    // 가디언 대시보드용 조회 (S15P11E102-221).
    List<CareRecord> findBySeniorId(UUID seniorId);

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
}
