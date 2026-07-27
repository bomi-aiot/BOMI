package com.ssafy.bomi.care.repository;

import com.ssafy.bomi.care.domain.CareRecord;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CareRecordRepository extends JpaRepository<CareRecord, UUID> {
}
