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
 * <p><b>Writes never pretend to succeed.</b> When no store is configured, the vector has the
 * wrong dimension, or Qdrant rejects the request, {@link #upsert} returns an explicit
 * {@link VectorWriteStatus}. The caller may only mark PostgreSQL {@code SYNCED} after
 * {@link VectorWriteStatus#STORED}. This keeps the derived-index bookkeeping truthful and
 * makes a later reindex possible.</p>
 */
public interface VectorStore {

    /**
     * Result of one vector write.
     *
     * <p>{@code UNAVAILABLE} and {@code RETRYABLE_FAILURE} leave PostgreSQL due for a later
     * run. {@code DIMENSION_MISMATCH} is not retryable until configuration is corrected, so
     * the sync service isolates that row as {@code FAILED} instead of paying for it every
     * schedule tick.</p>
     */
    enum VectorWriteStatus {
        STORED(false),
        UNAVAILABLE(true),
        RETRYABLE_FAILURE(true),
        DIMENSION_MISMATCH(false);

        private final boolean retryable;

        VectorWriteStatus(boolean retryable) {
            this.retryable = retryable;
        }

        public boolean stored() {
            return this == STORED;
        }

        public boolean retryable() {
            return retryable;
        }
    }

    /**
     * One candidate: an id and how close it was. Never any content.
     *
     * @param id the primary key of the authoritative row this vector was built from
     * @param score higher is closer. Cosine similarity, so 0.0–1.0 for normalized vectors
     */
    record VectorHit(UUID id, double score) {}

    /** One vector-query execution, separate from an empty successful result. */
    enum VectorSearchStatus {
        COMPLETED,
        UNAVAILABLE,
        FAILED,
        DIMENSION_MISMATCH
    }

    /**
     * Result of one vector query.
     *
     * <p>An empty {@code hits} list with {@code COMPLETED} means Qdrant was searched and
     * found no neighbours. The other statuses mean no trustworthy conclusion can be drawn
     * from an empty list.</p>
     */
    record VectorSearchResult(List<VectorHit> hits, VectorSearchStatus status) {
        public VectorSearchResult {
            hits = List.copyOf(hits);
        }

        public boolean completed() {
            return status == VectorSearchStatus.COMPLETED;
        }
    }

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
    VectorWriteStatus upsert(VectorCollection collection, UUID id, UUID seniorId,
        float[] vector);

    /**
     * Finds the ids whose vectors are closest to {@code queryVector}.
     *
     * <p><b>The {@code seniorId} filter here is an efficiency measure, not a privacy
     * boundary.</b> The payload can be stale — a memory whose visibility changed after it
     * was indexed still carries the old payload. The caller re-checks against PostgreSQL,
     * and that check is the actual boundary (see {@code ConversationContextService}).</p>
     *
     * @param limit ask for more than needed; the authoritative filter will remove some
     * @return an explicit execution status plus possibly-empty hits
     */
    VectorSearchResult search(VectorCollection collection, UUID seniorId, float[] queryVector,
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
