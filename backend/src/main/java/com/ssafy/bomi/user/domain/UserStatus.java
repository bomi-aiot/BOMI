package com.ssafy.bomi.user.domain;

/**
 * Lifecycle status of an {@link AppUser}.
 *
 * <p>Only {@code ACTIVE} is confirmed by the SQL default. Additional values are
 * provisional and must be reconciled with the finalized ERD.</p>
 */
public enum UserStatus {
    ACTIVE,
    INACTIVE
}
