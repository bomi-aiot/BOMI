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
 * <p>The corpus itself is not built yet — its source and chunking are still open
 * (CLAUDE.md §24) — so the default implementation reports unavailable.</p>
 */
public interface DocumentCorpusSearch {

    /**
     * One retrieved chunk.
     *
     * @param title human-readable source label, e.g. a programme name
     * @param content the chunk text that will be pasted into the prompt
     * @param sourceRef where it came from, so an answer can be traced back
     */
    record DocumentHit(String title, String content, String sourceRef) {}

    List<DocumentHit> search(String query, int limit);

    /** Whether a real corpus is wired up. Reported to the caller verbatim. */
    boolean isAvailable();
}
