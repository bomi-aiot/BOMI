package com.ssafy.bomi.relationship.domain;

/**
 * Priority of a guardian within a {@link CareRelationship}.
 *
 * <p>Only {@code PRIMARY} is confirmed by the SQL default; additional values are
 * provisional and must be reconciled with the finalized ERD.</p>
 */
public enum RelationshipPriority {
    PRIMARY,
    SECONDARY
}
