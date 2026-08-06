package com.ssafy.bomi.fact.domain;

/**
 * Processing stage of a {@link FactCandidate} (§6, §10).
 *
 * <p>Distinct from {@code coordination_status} (the PRIMARY-coordination stage);
 * the two must not be conflated. Only a {@code confirmed_value} may be
 * materialized.</p>
 */
public enum FactCandidateStatus {
    CAPTURED,
    NEEDS_CLARIFICATION,
    NEEDS_CONFIRMATION,
    COORDINATION_REQUIRED,
    CONFIRMED,
    MATERIALIZED,
    REJECTED,
    EXPIRED,

    /**
     * 어르신 본인이 "기억하지 마"로 지운 후보 (S15P11E102-348).
     *
     * <p>{@link #REJECTED}(보호자·시스템의 거절)와 구분한다 — 누가 왜 닫았는지가
     * 다르고, T4 신뢰("지웠다"는 약속)의 근거가 되는 값이라 섞으면 안 된다.
     * 재질의·확인요청·대시보드의 열림 판정은 전부 화이트리스트라 이 값은
     * 자동으로 제외된다. 물리 삭제가 아닌 상태 전이인 이유: 감사 이력을
     * 보존하면서 어떤 경로로도 다시 살아나지 않게 하기 위해서다.</p>
     */
    CANCELLED_BY_SENIOR
}
