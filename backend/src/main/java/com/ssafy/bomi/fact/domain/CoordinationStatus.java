package com.ssafy.bomi.fact.domain;

/**
 * Senior/PRIMARY coordination stage of a {@link FactCandidate} (§7, §10).
 *
 * <p>{@code NOT_REQUIRED} is the resting default when no coordination is needed.
 * PRIMARY priority is the priority of a final decision reached after coordination
 * and responsibility confirmation, not a silent immediate overwrite.</p>
 */
public enum CoordinationStatus {
    NOT_REQUIRED,
    COORDINATION_REQUIRED,
    WAITING_PRIMARY_GUARDIAN,
    WAITING_SENIOR,
    AGREED,
    DISAGREED,
    SENIOR_UNREACHABLE,
    GUARDIAN_OVERRIDE_CONFIRMED,
    COMPLETED
}
