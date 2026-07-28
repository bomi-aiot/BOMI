package com.ssafy.bomi.user.domain;

/**
 * Lifecycle status of an {@link AppUser}.
 *
 * <p>Values follow the {@code APP_USER_ENUM} code dictionary of the MVP ERD
 * ({@code status}); {@code ACTIVE} is the SQL default.</p>
 */
public enum UserStatus {
    ACTIVE,
    SUSPENDED,
    WITHDRAWN
}
