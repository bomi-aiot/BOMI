package com.ssafy.bomi.memory;

import static org.assertj.core.api.Assertions.assertThat;

import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import com.ssafy.bomi.memory.domain.MemoryType;
import com.ssafy.bomi.memory.domain.MemoryVerificationStatus;
import com.ssafy.bomi.memory.domain.MemoryVisibility;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@ActiveProfiles("datajpa")
class MemoryRepositoryTest {

    @Autowired MemoryRepository memoryRepository;
    @Autowired TestEntityManager em;

    @Test
    void persistsKeywordsArrayAndDefaults() {
        Memory memory = Memory.create(UUID.randomUUID(), MemoryType.HOBBY, "매일 아침 공원을 산책한다");
        memory.updateKeywords(List.of("산책", "공원", "아침"));
        memory.setImportance((short) 3);
        Memory saved = memoryRepository.saveAndFlush(memory);
        em.clear();

        Memory found = memoryRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getMemoryType()).isEqualTo(MemoryType.HOBBY);
        assertThat(found.getKeywords()).containsExactly("산책", "공원", "아침");
        assertThat(found.getImportance()).isEqualTo((short) 3);
        assertThat(found.getVerificationStatus()).isEqualTo(MemoryVerificationStatus.UNVERIFIED);
        assertThat(found.getLifecycleStatus()).isEqualTo(MemoryLifecycleStatus.ACTIVE);
        assertThat(found.getVisibility()).isEqualTo(MemoryVisibility.PRIVATE);
        assertThat(found.getFirstObservedAt()).isNotNull();
    }

    @Test
    void supersedeMarksLifecycleAndUniqueSourceCandidate() {
        UUID seniorId = UUID.randomUUID();
        UUID newerId = UUID.randomUUID();
        Memory older = Memory.create(seniorId, MemoryType.PREFERENCE, "커피를 좋아한다",
            MemoryVisibility.SHARED_WITH_PRIMARY);
        older.attachSources(null, null, UUID.randomUUID());
        older.supersededBy(newerId);
        Memory saved = memoryRepository.saveAndFlush(older);
        em.clear();

        Memory found = memoryRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getVisibility()).isEqualTo(MemoryVisibility.SHARED_WITH_PRIMARY);
        assertThat(found.getLifecycleStatus()).isEqualTo(MemoryLifecycleStatus.SUPERSEDED);
        assertThat(found.getSupersededById()).isEqualTo(newerId);
        assertThat(found.getSourceCandidateId()).isNotNull();
    }
}
