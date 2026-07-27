package com.ssafy.bomi.user.domain;

/**
 * Consent state shared by the personalization, health-data, schedule and
 * guardian-sharing consent columns of {@link AppUser}.
 *
 * <p>{@code NOT_REQUESTED} is the SQL default for the {@link AppUser} consent
 * columns. {@code GRANTED}/{@code DENIED}/{@code REVOKED} mirror the consent
 * lifecycle in the MVP ERD code dictionary. (The dedicated care-management
 * permission uses {@code CareManagementPermissionStatus}, whose unrequested
 * value is {@code NOT_ASKED}.)</p>
 */
public enum ConsentStatus {
    NOT_REQUESTED,
    GRANTED,
    DENIED,
    REVOKED
}
