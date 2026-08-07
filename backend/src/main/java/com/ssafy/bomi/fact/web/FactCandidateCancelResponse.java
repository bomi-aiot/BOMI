package com.ssafy.bomi.fact.web;

/**
 * 취소 결과 (S15P11E102-348). 닫힌 후보 개수만 돌려준다.
 *
 * <p>0 은 오류가 아니다 — 이 대화에서 아직 굳지 않은 후보가 없었다는 뜻이다
 * (이미 취소됐거나, 애초에 제출된 것이 없거나, 전부 확정 이후 단계다).</p>
 */
public record FactCandidateCancelResponse(int cancelledCount) {
}
