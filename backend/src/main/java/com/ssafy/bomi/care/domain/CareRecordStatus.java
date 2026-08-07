package com.ssafy.bomi.care.domain;

/**
 * Lifecycle status of a {@link CareRecord}.
 *
 * <p>Values follow the MVP ERD code dictionary (§8, §10). {@code ACTIVE} is the
 * SQL default. A confirmed value is never mutated in place: a change creates a
 * new row linked by {@code parent_record_id}, and the previous row becomes
 * {@code SUPERSEDED}.</p>
 */
public enum CareRecordStatus {
    ACTIVE,
    COMPLETED,
    CANCELLED,
    SUPERSEDED
}
