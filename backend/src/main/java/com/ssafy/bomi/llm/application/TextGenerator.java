package com.ssafy.bomi.llm.application;

/**
 * Turns a prompt into free-form text (S15P11E102-254).
 *
 * <p><b>The backend's first generative call.</b> Every other external dependency here is
 * either a lookup (Qdrant search) or a transform with a fixed output shape (Upstage
 * embeddings). A text generator is different: it produces prose that gets stored
 * ({@code conversation_summary.content}) and later fed back into a prompt. That is exactly
 * the shape CLAUDE.md §16 calls a generation call, so callers get <b>one</b> call per
 * conversation summarised, not one per retry or per candidate phrasing.</p>
 *
 * <p><b>Calls cost money, same as embedding.</b> {@code LlmProperties} enforces the same two
 * brakes {@code EmbeddingProperties} does: off by default, and a hard cap on how many calls
 * one scheduled run may make. Both are enforced by the caller (the sweep job), not here —
 * this interface only knows how to make one call.</p>
 *
 * <p><b>Must run off the turn path.</b> A generation round trip can run several seconds, far
 * outside the ~2s turn budget (CLAUDE.md §18), and outside any database transaction — see
 * {@code ConversationSummaryService} for why holding a Hikari connection for that long would
 * make ordinary context assembly queue behind it.</p>
 */
public interface TextGenerator {

    /**
     * Thrown when a prompt could not be turned into text.
     *
     * <p>The caller decides what "failed" means for its own flow. For conversation
     * summaries that is: log it, leave the conversation exactly as closed as it already
     * is, and let the next sweep try again (S15P11E102-254 완료 조건 — a summary failure
     * must never touch the conversation's own lifecycle or the senior's turn).</p>
     */
    class GenerationFailedException extends RuntimeException {
        public GenerationFailedException(String message, Throwable cause) {
            super(message, cause);
        }

        public GenerationFailedException(String message) {
            super(message);
        }
    }

    /**
     * Generates text for one prompt.
     *
     * <p>Synchronous and single-shot — no streaming, no retry. Retrying a generation call
     * inside a metered API is how a stuck sweep drains a budget; the sweep's own next tick
     * is the retry mechanism (same reasoning as {@code UpstageEmbeddingClient}).</p>
     *
     * @param prompt the fully assembled prompt. Callers build this themselves — this
     *     interface does not know what it is summarising.
     * @return the model's text, trimmed. Never blank; a blank result is treated as a
     *     failure (see {@link GenerationFailedException}).
     */
    String generate(String prompt);

    /**
     * Whether generation can run at all.
     *
     * <p>False when no API key is configured or the feature is switched off. Both are
     * supported states: callers must degrade (skip summarising, keep the conversation
     * closed) rather than fail the turn or the sweep.</p>
     */
    boolean isAvailable();
}
