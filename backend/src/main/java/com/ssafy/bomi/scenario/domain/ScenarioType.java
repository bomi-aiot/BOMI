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
    /** 낙상 대응 — value reserved; flow not implemented yet. */
    FALL_RESPONSE,
    /** 수동 상호작용 — value reserved; flow not implemented yet. */
    MANUAL_INTERACTION
}
