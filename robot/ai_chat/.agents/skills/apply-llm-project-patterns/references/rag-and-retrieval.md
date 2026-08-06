# RAG and Retrieval

Use these cards to improve an existing vertical slice. Do not add every gate at once.

## Contents

- Preserve source structure
- Chunk by retrieval unit
- Establish a 2-Step baseline
- Add relevance and query rewrite
- Add Self-RAG gates
- Add corrective external fallback
- Make retrieval tools answer directly

## Pattern: preserve source structure

- **Problem:** Extraction destroys tables, headings, or relationships needed for retrieval.
- **Use when:** Documents contain visual layout, tables, multi-column text, or scanned pages.
- **Do not use when:** Clean text already preserves the semantic units.
- **Signals:** Retrieved text loses row/column meaning; answers omit data visible in the source.
- **Minimum design:** Keep the original → extract to inspectable text/Markdown → compare representative pages → attach source metadata.
- **Lecture tips:** Vision-based PDF preprocessing can help; a Markdown loader may flatten tables. Inspect raw Markdown and loader output before choosing a workaround.
- **Comments:** Mark why a parser was chosen and what structure must survive replacement.
- **Failure modes:** Renaming extensions without testing; discarding page/source IDs; indexing OCR garbage.
- **Checks:** Representative headings and tables remain readable; extraction is reproducible.
- **Tests:** Text page, table page, scanned page, empty page, malformed file.
- **Escalate when:** Layout cannot be preserved without a document-specific parser or vision model.
- **Simplify when:** Direct API/database access provides the same facts more reliably.
- **Source:** `2.2`, cells covering Zerox preprocessing and `UnstructuredMarkdownLoader` table-loss comparison.

## Pattern: chunk by retrieval unit

- **Problem:** Retrieved chunks are too broad, too fragmented, or lose context.
- **Use when:** A corpus must be embedded or searched semantically.
- **Do not use when:** Records already have precise fields and query semantics.
- **Signals:** Relevant chunks rank low; answers need adjacent chunks; citations are too coarse.
- **Minimum design:** Define semantic unit → split with metadata → index → inspect top results for a fixed query set.
- **Lecture tips:** The lecture starts with recursive splitting around 1500 characters, 100 overlap, and paragraph/newline separators; treat these as a baseline, not a universal default.
- **Comments:** Explain the retrieval unit and which evaluation justifies size/overlap.
- **Failure modes:** Tuning chunk size without retrieval metrics; losing headings; duplicate overlap dominating top-k.
- **Checks:** Each chunk has stable ID, source, and location; top results contain sufficient answer evidence.
- **Tests:** Exact term, paraphrase, cross-section question, table lookup, no-match query.
- **Escalate when:** Metadata filters, parent-child retrieval, reranking, or hybrid search improves measured misses.
- **Simplify when:** Smaller atomic records answer the same queries.
- **Source:** `2.2`, loader, recursive splitter, embeddings, Chroma, and similarity-search cells.

## Pattern: establish a 2-Step baseline

- **Problem:** Generation quality is unknown because retrieval and answer behavior are entangled.
- **Use when:** Every supported question should consult one corpus.
- **Do not use when:** The question is outside the corpus boundary or retrieval is optional.
- **Signals:** Need a cheap, inspectable baseline before agentic routing.
- **Minimum design:** Query → top-k retrieval → context formatting → grounded prompt → answer/abstain.
- **Lecture tips:** Start with a small `k` such as three, inspect the hub prompt before adapting it, and keep query/context/answer distinct.
- **Comments:** Mark knowledge boundary, abstention behavior, and current top-k rationale.
- **Failure modes:** Passing all documents; treating a plausible answer as grounded; hiding retrieved evidence.
- **Checks:** Answer claims map to retrieved chunks; unsupported questions abstain.
- **Tests:** Answerable, unanswerable, conflicting evidence, duplicated chunks, retrieval timeout.
- **Escalate when:** A fixed evaluation set shows recoverable query or relevance failures.
- **Simplify when:** One deterministic lookup replaces semantic retrieval.
- **Source:** `2.2`, typed RAG state, retrieval/generation nodes, `add_sequence`, and compiled graph cells.

## Pattern: add relevance and query rewrite

- **Problem:** The original query retrieves irrelevant evidence but can be reformulated.
- **Use when:** Error analysis shows vocabulary mismatch or underspecified queries.
- **Do not use when:** Missing knowledge, permissions, or indexing defects cause the miss.
- **Signals:** Human rewrite retrieves the right chunk; domain synonyms are known.
- **Minimum design:** Retrieve → structured relevance grade → answer or bounded rewrite → retrieve again.
- **Lecture tips:** Route rewrite back to retrieval, not directly to generation; inject a domain dictionary only when it improves a fixed set.
- **Comments:** Explain rewrite budget, preserved intent, and domain-term mapping.
- **Failure modes:** Official example wiring ends after rewrite; semantic drift; endless retrieve-rewrite cycles.
- **Checks:** Rewritten query preserves constraints; retry count and final reason are visible.
- **Tests:** Synonym recovery, already-good query, unrecoverable miss, rewrite drift, max retries.
- **Escalate when:** Relevance remains weak after indexing and query fixes.
- **Simplify when:** Deterministic alias expansion solves the measured cases.
- **Source:** `2.3`, official Agentic RAG comparison, document grader, rewrite prompt, and corrected edge discussion.

## Pattern: add Self-RAG gates

- **Problem:** Relevant-looking context can still produce unsupported or unhelpful answers.
- **Use when:** Grounding and usefulness failures are separately measurable and high impact.
- **Do not use when:** The baseline lacks retrieval fixtures or extra model calls exceed constraints.
- **Signals:** Answers cite irrelevant text, hallucinate beyond context, or fail the user despite being grounded.
- **Minimum design:** Relevance grade → generate → grounding grade → usefulness grade → answer, regenerate, rewrite, or stop within budgets.
- **Lecture tips:** Return semantic labels such as `relevant` and map them to nodes; use pass-through nodes when they make the graph inspectable.
- **Comments:** State each grader’s contract, threshold, retry owner, and stop reason.
- **Failure modes:** Graders share the same blind spot; labels contain typos; regeneration and rewrite loops are unbounded.
- **Checks:** Every grade is traceable; uncertain grader output fails safely; loops terminate.
- **Tests:** Irrelevant docs, grounded/helpful, grounded/unhelpful, unsupported answer, malformed grade, budget exhaustion.
- **Escalate when:** Independent or deterministic validators are required for risk.
- **Simplify when:** One retrieval-quality gate prevents the observed errors.
- **Source:** `2.4`, relevance, hallucination, answer graders, semantic routing, and pass-through graph cells.

## Pattern: add corrective external fallback

- **Problem:** The local corpus lacks relevant or sufficiently current evidence.
- **Use when:** External search is permitted and freshness is part of the product contract.
- **Do not use when:** Data must remain private, external sources are untrusted, or local completeness is promised.
- **Signals:** Relevance grade identifies a true corpus gap; web results can be attributed.
- **Minimum design:** Local retrieve → relevance decision → optional rewrite → external search → normalize evidence → grounded answer.
- **Lecture tips:** Trigger web search only after missing/irrelevant local evidence; keep local and external provenance distinct.
- **Comments:** Mark data-egress rule, freshness boundary, source allowlist, and fallback budget.
- **Failure modes:** Searching by default; leaking sensitive queries; typoed route labels; mixing untrusted text into instructions.
- **Checks:** External calls are observable; sources and timestamps survive; prompt injection is treated as data.
- **Tests:** Local hit, corpus miss, search failure, malicious page text, stale result, egress-denied request.
- **Escalate when:** Trusted-source connectors or human approval are required.
- **Simplify when:** A scheduled ingestion job can keep the local corpus current.
- **Source:** `2.5`, document relevance routing and web-search correction cells.

## Pattern: make retrieval tools answer directly

- **Problem:** A tool-using agent summarizes retrieved text instead of answering the user’s question.
- **Use when:** Retrieval is optional among tools and the agent must synthesize a direct answer.
- **Do not use when:** Retrieval is always required; prefer the simpler 2-Step baseline.
- **Signals:** Output describes documents but omits the requested fact or invents missing details.
- **Minimum design:** Precise retriever-tool description → retrieved evidence → system instruction to answer the question, cite evidence, and abstain when insufficient.
- **Lecture tips:** Explicitly say “answer the question, do not merely summarize”; keep the insufficiency rule.
- **Comments:** Explain the direct-answer invariant and evidence boundary.
- **Failure modes:** Overbroad tool description; summary-shaped output; fabrication when retrieval is empty.
- **Checks:** The final response addresses the original request; evidence remains inspectable.
- **Tests:** Direct fact, synthesis, empty result, conflicting chunks, irrelevant result.
- **Escalate when:** Retrieval relevance must be graded or rewritten.
- **Simplify when:** The agent always calls retrieval, so a fixed RAG path is clearer.
- **Source:** `부록1`, retriever tool, observed summarization failure, and corrected agent prompt cells.

