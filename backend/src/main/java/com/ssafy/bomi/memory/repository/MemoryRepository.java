package com.ssafy.bomi.memory.repository;

import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MemoryRepository extends JpaRepository<Memory, UUID> {

    List<Memory> findTop5BySeniorIdAndLifecycleStatusOrderByFirstObservedAtDesc(
            UUID seniorId, MemoryLifecycleStatus lifecycleStatus);
}
