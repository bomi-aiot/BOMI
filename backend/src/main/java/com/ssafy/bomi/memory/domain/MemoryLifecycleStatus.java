package com.ssafy.bomi.memory.domain;

/**
 * Lifecycle state of a {@link Memory}.
 *
 * <p>Values follow the {@code MEMORY_ENUM} code dictionary of the MVP ERD.
 * {@code ACTIVE} is the SQL default. Only {@code ACTIVE} memories are eligible
 * for retrieval; a change is expressed as a new memory plus
 * {@code superseded_by_id} (§4).</p>
 */
public enum MemoryLifecycleStatus {
    ACTIVE,
    DISPUTED,
    SUPERSEDED,
    EXPIRED,
    DELETED
}
