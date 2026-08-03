package com.ssafy.bomi.scenario.domain;

/**
 * Type of robot behavior flow a {@link Scenario} represents.
 *
 * <p>Values follow the {@code SCENARIO_ENUM} code dictionary of the MVP ERD.</p>
 *
 * <p><b>Scope note (this sprint):</b> only the {@link #HOMECOMING} flow has a
 * defined transition path in {@link ScenarioStatus}. {@link #FALL_RESPONSE} and
 * {@link #MANUAL_INTERACTION} are reserved values only — their flows are added on
 * top of the shared transition map in a follow-up sprint.</p>
 */
public enum ScenarioType {
    /** 귀가 환영 — fully implemented this sprint. */
    HOMECOMING,
    /**
     * 온습도 이상 안부 확인 — 온습도 관측이 임계값을 넘으면 어르신에게 이동해
     * 안부를 묻는다. 상태 경로는 HOMECOMING 과 같은 선형 경로를 공유한다
     * (MOVING_TO_ENTRANCE 는 "시나리오 목적지로 이동 중"의 범용 의미로 쓴다).
     */
    WELLNESS_CHECK,
    /** 낙상 대응 — value reserved; flow not implemented yet. */
    FALL_RESPONSE,
    /** 수동 상호작용 — value reserved; flow not implemented yet. */
    MANUAL_INTERACTION
}
