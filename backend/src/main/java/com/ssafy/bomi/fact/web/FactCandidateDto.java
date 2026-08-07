package com.ssafy.bomi.fact.web;

import java.util.Map;

/**
 * 확인요청 응답 DTO. FE 계약(frontend/src/services/mappers/confirmationRequest.ts 의
 * FactCandidateDto)과 1:1 로 맞춘 모양이다. 서버는 fact_candidate 원본 enum/필드를 그대로
 * 내보내고, 화면 표시값(status/kind)으로의 변환은 FE 매퍼가 담당한다(계약퍼스트).
 *
 * <p>enum·UUID·시각은 모두 문자열로 직렬화한다(FE camelCase 계약과 일치).
 * {@code title/summary/question/evidence} 는 DB 컬럼이 아니라 서버가 생성하는 표시 문구.</p>
 */
public record FactCandidateDto(
        String id,
        String seniorId,
        String targetDomain,
        String factType,
        String operation,
        String status,
        String riskLevel,
        String coordinationStatus,
        String sourceType,
        String conversationId,
        String sourceMessageId,
        Map<String, Object> proposedValue,
        Map<String, Object> confirmedValue,
        Map<String, Object> currentValue,
        String title,
        String summary,
        String question,
        String evidence,
        String materializedTargetId,
        String createdAt,
        String confirmedAt,
        String materializedAt) {
}
