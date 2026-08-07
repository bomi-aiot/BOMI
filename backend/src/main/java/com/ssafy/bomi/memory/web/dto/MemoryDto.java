package com.ssafy.bomi.memory.web.dto;

import java.util.List;

/**
 * 기억(memory) 응답 DTO. FE 대화 정보/기억(ConversationPreference) 화면용.
 * memory 원본 필드를 그대로 내보내고, FE 매퍼가 title/isEnabled 등을 파생한다(계약퍼스트).
 *
 * <p>주의: memory 테이블에는 title/isEnabled 컬럼이 없다. title 은 FE 가 keywords/content 로
 * 파생하고, isEnabled 는 lifecycleStatus(ACTIVE 여부)로 파생한다.</p>
 */
public record MemoryDto(
        String id,
        String seniorId,
        String memoryType,
        String content,
        List<String> keywords,
        String visibility,
        String verificationStatus,
        String lifecycleStatus,
        String sourceConversationId,
        String firstObservedAt,
        String lastConfirmedAt) {
}
