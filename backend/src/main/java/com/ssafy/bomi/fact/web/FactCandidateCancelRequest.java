package com.ssafy.bomi.fact.web;

import jakarta.validation.constraints.NotNull;
import java.util.UUID;

/**
 * "기억하지 마" — 한 대화의 미확정 사실 후보를 닫아 달라는 로봇 요청 (S15P11E102-348).
 *
 * <p>후보 id 가 아니라 대화 단위인 이유 — 로봇은 서버가 배정한 후보 id 를 모르고,
 * 로봇 쪽 절반({@code extraction.forget_conversation})도 대화 단위로 동작한다.</p>
 */
public record FactCandidateCancelRequest(
        @NotNull UUID seniorId,
        @NotNull UUID conversationId) {
}
