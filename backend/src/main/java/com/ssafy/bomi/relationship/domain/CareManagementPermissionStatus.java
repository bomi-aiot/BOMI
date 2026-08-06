package com.ssafy.bomi.relationship.domain;

/**
 * Status of the delegated care-management permission on a {@link CareRelationship}.
 *
 * <p>Values follow the {@code care_relationship.care_management_permission_status}
 * code dictionary of the MVP ERD (§10). Only a guardian that is
 * {@code status=ACTIVE}, {@code priority=PRIMARY} and {@code GRANTED} may proxy
 * confirm/register/modify sensitive information (§7). {@code NOT_ASKED} applies
 * when there is no PRIMARY guardian to ask.</p>
 */
public enum CareManagementPermissionStatus {
    NOT_ASKED,
    GRANTED,
    DENIED,
    REVOKED
}
