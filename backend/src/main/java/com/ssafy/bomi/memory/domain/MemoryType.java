package com.ssafy.bomi.memory.domain;

/**
 * Category of a long-term {@link Memory}.
 *
 * <p>Values follow the {@code MEMORY_ENUM} code dictionary of the MVP ERD.</p>
 */
public enum MemoryType {
    PERSONAL_RELATIONSHIP,
    PREFERENCE,
    HOBBY,
    DAILY_ROUTINE,
    LIFE_EVENT,
    FAMILY_MEMORY,
    EMOTIONAL_EVENT,
    CONVERSATION_SUMMARY,
    OTHER
}
