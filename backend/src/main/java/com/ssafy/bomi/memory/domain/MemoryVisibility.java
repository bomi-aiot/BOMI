package com.ssafy.bomi.memory.domain;

/**
 * Sharing scope of a {@link Memory}.
 *
 * <p>Values follow the {@code MEMORY_ENUM} code dictionary of the MVP ERD.
 * {@code PRIVATE} is the SQL default. Retrieval must respect the requester's
 * allowed visibility (§4).</p>
 */
public enum MemoryVisibility {
    PRIVATE,
    SHARED_WITH_PRIMARY,
    SHARED_WITH_GUARDIANS
}
