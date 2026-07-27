package com.ssafy.bomi.memory.repository;

import com.ssafy.bomi.memory.domain.Memory;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MemoryRepository extends JpaRepository<Memory, UUID> {
}
