package com.ssafy.bomi.embedding.domain;

/**
 * Sync state of a row's vector in the external vector store.
 *
 * <p>Semantic search does <strong>not</strong> run in this database. Upstage
 * embeddings are 4096-dimensional, and pgvector can only index up to 2,000
 * ({@code vector}) or 4,000 ({@code halfvec}) dimensions, so an index is
 * impossible and only a sequential scan would remain. Korean quality made the
 * model non-negotiable, so the vectors live in an external store (Qdrant) and this
 * database stays the authority on the content itself (S15P11E102-218).</p>
 *
 * <p>That makes the vector store a <em>derived index</em>. This status is how we
 * know what to rebuild when it is lost, and how a partial failure stays visible
 * instead of silently degrading search quality.</p>
 *
 * <p>Shared by {@code memory} and {@code conversation_summary} — the only two
 * things that are retrieved by similarity (CLAUDE.md §8).</p>
 */
public enum EmbeddingStatus {

    /** Never embedded yet. The default for new and pre-migration rows. */
    PENDING,

    /** Present in the vector store and current. */
    SYNCED,

    /**
     * Needs re-embedding because the content changed or the embedding model
     * changed. A vector from a different model sits in a different vector space,
     * which makes its similarity scores meaningless.
     */
    STALE,

    /**
     * Attempted and failed. Kept distinct from {@code PENDING} so a permanently
     * failing row is visible instead of being retried forever as if it were new.
     */
    FAILED
}
