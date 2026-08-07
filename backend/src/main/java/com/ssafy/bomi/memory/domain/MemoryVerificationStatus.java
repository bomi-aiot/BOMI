package com.ssafy.bomi.memory.domain;

/**
 * Verification state of a {@link Memory}.
 *
 * <p>Values follow the {@code MEMORY_ENUM} code dictionary of the MVP ERD.
 * {@code UNVERIFIED} is the SQL default. Retrieval filters out {@code REJECTED}
 * memories (§4).</p>
 */
public enum MemoryVerificationStatus {
    UNVERIFIED,
    AUTO_ACCEPTED,
    USER_CONFIRMED,
    GUARDIAN_CONFIRMED,
    REJECTED
}
