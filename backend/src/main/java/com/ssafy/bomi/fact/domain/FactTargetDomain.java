package com.ssafy.bomi.fact.domain;

/**
 * Domain a {@link FactCandidate} will be materialized into (§10).
 *
 * <p>Determines the logical target of {@code target_entity_id} /
 * {@code materialized_target_id}, which are logical references (not physical
 * FKs) that vary by this value.</p>
 */
public enum FactTargetDomain {
    PROFILE,
    CARE_RELATIONSHIP,
    MEMORY,
    CARE_RECORD
}
