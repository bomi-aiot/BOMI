package com.ssafy.bomi.memory.web;

import com.ssafy.bomi.memory.domain.Memory;
import com.ssafy.bomi.memory.domain.MemoryLifecycleStatus;
import com.ssafy.bomi.memory.repository.MemoryRepository;
import com.ssafy.bomi.memory.web.dto.MemoryDto;
import com.ssafy.bomi.user.repository.AppUserRepository;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 가디언 '대화 정보/기억' 조회 서비스. 단일 어르신 전제(P0). */
@Service
public class MemoryQueryService {

    private static final String SENIOR_USER_TYPE = "SENIOR";

    private final AppUserRepository appUserRepository;
    private final MemoryRepository memoryRepository;

    public MemoryQueryService(
            AppUserRepository appUserRepository, MemoryRepository memoryRepository) {
        this.appUserRepository = appUserRepository;
        this.memoryRepository = memoryRepository;
    }

    @Transactional(readOnly = true)
    public List<MemoryDto> getConversationMemories() {
        UUID seniorId = appUserRepository.findFirstByUserType(SENIOR_USER_TYPE)
                .orElseThrow(() -> new IllegalStateException("등록된 어르신이 없습니다."))
                .getId();
        return memoryRepository.findBySeniorIdOrderByFirstObservedAtDesc(seniorId).stream()
                .filter(m -> m.getLifecycleStatus() != MemoryLifecycleStatus.DELETED)
                .map(MemoryQueryService::toDto)
                .toList();
    }

    static MemoryDto toDto(Memory m) {
        return new MemoryDto(
                m.getId().toString(),
                m.getSeniorId().toString(),
                m.getMemoryType() == null ? null : m.getMemoryType().name(),
                m.getContent(),
                m.getKeywords(),
                m.getVisibility() == null ? null : m.getVisibility().name(),
                m.getVerificationStatus() == null ? null : m.getVerificationStatus().name(),
                m.getLifecycleStatus() == null ? null : m.getLifecycleStatus().name(),
                m.getSourceConversationId() == null ? null : m.getSourceConversationId().toString(),
                iso(m.getFirstObservedAt()),
                iso(m.getLastConfirmedAt()));
    }

    private static String iso(OffsetDateTime value) {
        return value == null ? null : value.toString();
    }
}
