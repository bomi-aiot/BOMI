package com.ssafy.bomi.vector.application;

/**
 * The two things retrieved by similarity (S15P11E102-218).
 *
 * <p>An enum rather than free strings, because a typo in a collection name does not fail —
 * Qdrant simply reports nothing found, and the robot quietly stops remembering. There are
 * exactly two, and CLAUDE.md §8 says why: raw utterances are never retrieved by meaning
 * (they are the evidence, not the answer), and care records are retrieved by structure.</p>
 */
public enum VectorCollection {

    /** Long-term memories. The authority is {@code memory} in PostgreSQL. */
    MEMORY("memory"),

    /** Conversation and daily summaries. The authority is {@code conversation_summary}. */
    CONVERSATION_SUMMARY("conversation_summary");

    private final String collectionName;

    VectorCollection(String collectionName) {
        this.collectionName = collectionName;
    }

    public String collectionName() {
        return collectionName;
    }
}
