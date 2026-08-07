package com.ssafy.bomi.fact.domain;

/**
 * Sensitivity level of a {@link FactCandidate} (§6, §10).
 *
 * <p>{@code SENSITIVE}/{@code HIGH} facts require explicit whole-content
 * confirmation before materialization.</p>
 */
public enum RiskLevel {
    NORMAL,
    SENSITIVE,
    HIGH
}
