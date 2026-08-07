package com.ssafy.bomi.relationship.domain;

/**
 * Lifecycle status of a {@link CareRelationship}.
 *
 * <p>Values follow the {@code CARE_RELATIONSHIP_ENUM} code dictionary of the MVP
 * ERD ({@code status}); {@code ACTIVE} is the SQL default.</p>
 */
public enum RelationshipStatus {
    PENDING,
    ACTIVE,
    DISCONNECT_REQUESTED,
    ENDED,
    REVOKED
}
