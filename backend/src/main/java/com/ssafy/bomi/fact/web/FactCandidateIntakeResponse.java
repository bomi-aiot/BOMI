package com.ssafy.bomi.fact.web;

import java.util.UUID;

/**
 * 사실 후보 제출 결과 (S15P11E102-255).
 *
 * <p>로봇은 이 id 를 따로 보관할 필요가 없다 — 큐 소비는 서버가 배치로 마저 처리하고,
 * 로봇은 "제출이 성공했다"는 사실만 알면 된다. 그럼에도 id 와 status 를 돌려주는 것은
 * 디버깅과 테스트에서 방금 만든 행을 바로 조회할 수 있게 하기 위해서다.</p>
 */
public record FactCandidateIntakeResponse(UUID id, String status) {
}
