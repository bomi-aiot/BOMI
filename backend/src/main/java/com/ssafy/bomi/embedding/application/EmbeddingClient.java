package com.ssafy.bomi.embedding.application;

/**
 * Turns text into a vector (S15P11E102-218).
 *
 * <p><b>Two methods, not one method with a flag.</b> Upstage ships a separate model for
 * stored text ({@code -passage}) and for search text ({@code -query}). They are trained as a
 * pair: a passage vector and a query vector for the same sentence are close, but two
 * passage vectors compared to each other mean something different. Mixing them does not
 * throw — it returns slightly worse neighbours forever, and nothing in the system can tell
 * you that happened. A boolean parameter is one typo away from that; two methods are
 * not.</p>
 *
 * <p><b>Calls cost money.</b> The API is metered and the project budget is small. Two things
 * follow, and they are enforced elsewhere rather than trusted here:</p>
 * <ul>
 *   <li>Stored text is embedded once. {@code embedding_status} and {@code embedding_model}
 *       (V5) are what make "once" checkable, so re-running a sync does not re-pay.</li>
 *   <li>The sync job has a hard per-run call ceiling. A loop that retries a permanently
 *       failing row is how a metered API drains a budget overnight.</li>
 * </ul>
 */
public interface EmbeddingClient {

    /**
     * Thrown when a vector could not be produced.
     *
     * <p>Checked at the call site rather than returning null: the two callers must do
     * different things. The sync job marks the row {@code FAILED} so it stays visible; the
     * turn path drops semantic ranking and answers anyway.</p>
     */
    class EmbeddingFailedException extends RuntimeException {
        public EmbeddingFailedException(String message, Throwable cause) {
            super(message, cause);
        }

        public EmbeddingFailedException(String message) {
            super(message);
        }
    }

    /**
     * Embeds text that is being <em>stored</em> — a memory, a summary.
     *
     * <p>Runs off the turn path only. Embedding yesterday's memory while the senior waits
     * for an answer spends their patience on our bookkeeping (CLAUDE.md §18).</p>
     */
    float[] embedPassage(String text);

    /**
     * Embeds text that is being <em>searched with</em> — what the senior just said.
     *
     * <p>This one is inside the turn budget. It is also the only embedding call that scales
     * with conversation volume, so it is the one that shows up on the bill.</p>
     */
    float[] embedQuery(String text);

    /**
     * The model id to record in {@code embedding_model} for a stored vector.
     *
     * <p>Recorded per row because a model change invalidates every existing vector — a
     * different model is a different vector space, and similarity across two spaces is
     * meaningless. This string is how the sync job knows which rows to redo.</p>
     */
    String passageModelId();

    /** Expected vector length. Must equal {@code bomi.qdrant.dimensions}. */
    int dimensions();

    /**
     * Whether embedding can run at all.
     *
     * <p>False when no API key is configured, or when the feature is switched off. Both are
     * supported states — retrieval degrades to keyword × importance × recency — and both are
     * announced at startup instead of showing up later as vague answer quality.</p>
     */
    boolean isAvailable();
}
