package com.ssafy.bomi.relationship.domain;

/**
 * Lifecycle status of a {@link CareRelationship}.
 *
 * <p>Only {@code ACTIVE} is confirmed by the SQL default; additional values are
 * provisional and must be reconciled with the finalized ERD.</p>
 */
public enum RelationshipStatus {
    ACTIVE,
    INACTIVE
}
