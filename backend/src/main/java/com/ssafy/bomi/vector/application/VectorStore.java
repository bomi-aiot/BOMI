package com.ssafy.bomi.vector.application;

import java.util.List;
import java.util.UUID;

/**
 * The vector store, behind a port (S15P11E102-218).
 *
 * <p><b>Why a port at all.</b> The store is a <em>derived index</em>; PostgreSQL is the
 * authority on content, visibility, and lifecycle. If Qdrant types leaked into the context
 * assembly, replacing the store would mean touching the retrieval rules — and those rules
 * are where the privacy decisions live. Same reason {@code notify/} sits behind an
 * adapter.</p>
 *
 * <p><b>What this port deliberately cannot do.</b> There is no "search and return content"
 * method. A hit is an id and a score, nothing more. The caller must go back to PostgreSQL
 * for the actual text and re-check whether it is still allowed to be read. Returning
 * content here would make it possible — easy, even — to answer a turn straight from a
 * payload that was written before the senior changed their mind about sharing.</p>
 *
 * <p><b>Every method may be a no-op.</b> When no store is configured, or the embedding model
 * has no API key, {@link #isAvailable()} is false and writes are dropped. That is not a
 * silent failure: the row keeps {@code embedding_status = PENDING}, so the sync job
 * reindexes it the moment the store comes back (V5 exists for exactly this).</p>
 */
public interface VectorStore {

    /**
     * One candidate: an id and how close it was. Never any content.
     *
     * @param id the primary key of the authoritative row this vector was built from
     * @param score higher is closer. Cosine similarity, so 0.0–1.0 for normalized vectors
     */
    record VectorHit(UUID id, double score) {}

    /**
     * Makes sure the collections exist with the right dimension.
     *
     * <p>Called once at startup. Idempotent — an existing collection is left alone rather
     * than recreated, because recreating drops every vector in it. A dimension mismatch is
     * reported rather than fixed: silently recreating would discard the whole index on a
     * config typo.</p>
     */
    void ensureCollections();

    /**
     * Stores or replaces one vector.
     *
     * @param seniorId goes into the payload as the one filter the store is trusted with.
     *     Not a privacy control — see {@link #search} — but without it every query would
     *     score every senior's memories against each other
     */
    void upsert(VectorCollection collection, UUID id, UUID seniorId, float[] vector);

    /**
     * Finds the ids whose vectors are closest to {@code queryVector}.
     *
     * <p><b>The {@code seniorId} filter here is an efficiency measure, not a privacy
     * boundary.</b> The payload can be stale — a memory whose visibility changed after it
     * was indexed still carries the old payload. The caller re-checks against PostgreSQL,
     * and that check is the actual boundary (see {@code ConversationContextService}).</p>
     *
     * @param limit ask for more than needed; the authoritative filter will remove some
     * @return possibly empty, never null. Empty when the store is unavailable
     */
    List<VectorHit> search(VectorCollection collection, UUID seniorId, float[] queryVector,
        int limit);

    /** Removes one vector, e.g. when its row was superseded or deleted. */
    void delete(VectorCollection collection, UUID id);

    /**
     * Whether a real store is reachable.
     *
     * <p>Exposed so the context response can tell the robot that retrieval ran without
     * semantic ranking. A handler that believes it has full memory speaks about the past
     * with more confidence than it has earned.</p>
     */
    boolean isAvailable();
}
