package com.ssafy.bomi.person.web.dto;

/**
 * 명부 조회 응답 DTO. {@code deceasedNote} 는 보호자 앱 화면에서만 쓰는 내부
 * 메모이며, 대화 문맥 API(ConversationContextResponse)에는 절대 실리지 않는다
 * (CLAUDE.md §8 — 회피는 정보가 아니라 금지문으로).
 */
public record KnownPersonDto(
        String id,
        String displayName,
        String relationship,
        Boolean isDeceased,
        String deceasedNote,
        Boolean livesWith,
        String contactFrequency,
        String createdAt,
        String updatedAt) {
}
