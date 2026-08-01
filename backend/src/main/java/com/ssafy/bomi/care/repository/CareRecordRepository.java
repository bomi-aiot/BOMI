package com.ssafy.bomi.care.repository;

import com.ssafy.bomi.care.domain.CareRecord;
import com.ssafy.bomi.care.domain.CareRecordStatus;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CareRecordRepository extends JpaRepository<CareRecord, UUID> {

    List<CareRecord> findBySeniorId(UUID seniorId);

    List<CareRecord> findBySeniorIdAndStatus(UUID seniorId, CareRecordStatus status);

    List<CareRecord> findBySeniorIdAndRecordTypeAndStatus(
            UUID seniorId, String recordType, CareRecordStatus status);
}
