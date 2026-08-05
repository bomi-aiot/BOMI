package com.ssafy.bomi.context.application;

import java.util.List;
import java.util.UUID;

/**
 * Semantic (vector) similarity search over long-term memories.
 *
 * <p>Why this is a port and not a method: the vectors do not live in this database.
 * Upstage embeddings are 4096-dimensional and pgvector indexes at most 2,000
 * ({@code vector}) or 4,000 ({@code halfvec}) dimensions, so semantic search moved
 * to an external vector store (S15P11E102-218). Until that lands, the context
 * assembly must still work — with less depth, but never silently.</p>
 *
 * <p>The pre-filter is deliberately <strong>not</strong> delegated here. Filtering by
 * {@code lifecycle_status}, {@code verification_status}, and {@code visibility} is a
 * privacy and correctness rule, and this database is its authority. An
 * implementation may narrow by {@code seniorId} for efficiency, but the caller
 * re-applies the authoritative filter afterwards: if a memory's visibility changed
 * after it was indexed, a stale copy in the vector store must not leak it.</p>
 */
public interface MemorySemanticSearch {

    /**
     * One candidate from the vector store.
     *
     * @param memoryId the {@code memory.id} the vector was built from
     * @param similarity 0.0–1.0, higher is closer in meaning
     */
    record SemanticHit(UUID memoryId, double similarity) {}

    /**
     * One query embedding applied to both personal-memory and conversation-summary indexes.
     *
     * @param semanticUsed at least one requested Qdrant collection completed its search
     * @param fallbackReason stable machine-readable degradation reason, or {@code null}
     * @param latencyMs embedding plus vector-search wall time
     */
    record SearchResult(
        List<SemanticHit> memoryHits,
        List<SemanticHit> summaryHits,
        boolean semanticUsed,
        String fallbackReason,
        long latencyMs
    ) {
        public SearchResult {
            memoryHits = List.copyOf(memoryHits);
            summaryHits = List.copyOf(summaryHits);
        }
    }

    /**
     * Finds memories whose meaning is closest to {@code query}.
     *
     * @param limit an upper bound on candidates; the caller asks for more than it
     *     needs because the authoritative filter will remove some
     * @return possibly empty, never {@code null}
     */
    SearchResult search(UUID seniorId, String query, int memoryLimit, int summaryLimit);

    /**
     * Whether a real vector store is wired up.
     *
     * <p>Exposed so the response can tell the robot that retrieval ran without
     * semantic ranking. The robot needs to know: a handler that thinks it has full
     * memory will speak about the past with more confidence than it has earned.</p>
     */
    boolean isAvailable();
}
