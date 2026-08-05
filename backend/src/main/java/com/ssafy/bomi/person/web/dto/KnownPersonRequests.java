package com.ssafy.bomi.person.web.dto;

/** 명부 등록·수정 요청 DTO. 생성과 수정 모두 같은 필드 집합을 쓴다(부분 갱신 없음). */
public class KnownPersonRequests {

    private KnownPersonRequests() {
    }

    public record CreateKnownPersonRequest(
            String displayName,
            String relationship,
            Boolean isDeceased,
            String deceasedNote,
            Boolean livesWith,
            String contactFrequency) {
    }

    public record UpdateKnownPersonRequest(
            String displayName,
            String relationship,
            Boolean isDeceased,
            String deceasedNote,
            Boolean livesWith,
            String contactFrequency) {
    }
}
