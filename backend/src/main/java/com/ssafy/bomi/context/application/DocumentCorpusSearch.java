package com.ssafy.bomi.context.application;

import java.util.List;

/**
 * Retrieval over the reference document corpus (welfare programmes, FAQs).
 *
 * <p>Separate from memory search because these are two different kinds of thing.
 * Memories are one senior's personal facts; documents are long public prose worth
 * chunking. Mixing them would let a leaflet about pension eligibility outrank
 * something the senior actually told us.</p>
 *
 * <p>Only requested for the {@code info} intent. Searching documents during small
 * talk spends latency the two-second turn budget does not have and pollutes the
 * prompt with text nobody asked about (CLAUDE.md §8, §16).</p>
 *
 * <p>The MVP implementation reads a small versioned corpus bundled with the service and
 * preserves source, chunk, citation and URL metadata. It is deliberately separate from
 * personal-memory vectors: public policy text has a different lifecycle and authority.</p>
 */
public interface DocumentCorpusSearch {

    /**
     * One retrieved chunk.
     *
     * @param title human-readable source label, e.g. a programme name
     * @param content the chunk text that will be pasted into the prompt
     * @param source publisher or source system
     * @param version source snapshot or policy version
     * @param chunkId stable chunk identifier
     * @param citation short human-readable citation label
     * @param url authoritative source URL
     */
    record DocumentHit(
        String title,
        String content,
        String source,
        String version,
        String chunkId,
        String citation,
        String url
    ) {}

    /** Completed result or a machine-readable degradation reason. */
    record SearchResult(
        List<DocumentHit> hits,
        boolean used,
        String fallbackReason,
        long latencyMs
    ) {
        public SearchResult {
            hits = List.copyOf(hits);
        }
    }

    SearchResult search(String query, int limit);

    /** Whether a real corpus is wired up. Reported to the caller verbatim. */
    boolean isAvailable();
}
