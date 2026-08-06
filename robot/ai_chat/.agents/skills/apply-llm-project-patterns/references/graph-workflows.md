# Graph Workflows

> **Repository precedence (BOMI / S15P11E102).** For the conversation runtime, `CLAUDE.md`
> is the authority (§6 graph structure, §7 gate, §16 LLM budget). Where this generic guide
> differs, **CLAUDE.md wins**:
> - **One generation LLM call per turn** (§16). Triage, intent classification, and
>   back-channel detection are local rules — never an extra model round trip, and never a
>   model router where a deterministic predicate works. The turn budget is ~2 s.
> - **Silence is a terminal state** (§7). "Not speaking" means never reaching `emit`; the
>   gate routes straight to `END`. That is a success path, not an error terminal.
> - `graph/build.py` holds **wiring only** — no business logic (§20).
> - The checkpointer is **robot-local SQLite**, never the server database (§5).
> - Prefer conditional execution over fan-out: parallel branches that each add an external
>   round trip will blow the §16 latency budget.
>
> Everything else below is compatible and still applies.

Use a graph to expose a real state lifecycle. Keep model judgment inside nodes or routers and keep graph control deterministic.

## Contents

- Define typed state and narrow nodes
- Route with semantic decisions
- Bound every cycle
- Parallelize independent work
- Compose subgraphs deliberately
- Stream for diagnosis

## Pattern: define typed state and narrow nodes

- **Problem:** Hidden data flow makes orchestration difficult to test and inspect.
- **Use when:** Several steps share durable or observable state.
- **Do not use when:** Local variables in one function express the flow clearly.
- **Signals:** Named stages, branching, resume, per-step traces, or parallel joins.
- **Minimum design:** Typed state → single-purpose node functions → partial updates → explicit `START`/`END` → compile.
- **Lecture tips:** Distinguish state, node, normal edge, and conditional edge; render the compiled graph as a pre-execution review.
- **Comments:** Mark state-field ownership and invariants, not the syntax of `add_node`.
- **Failure modes:** One “god state”; nodes overwrite unrelated fields; implicit entry/exit obscures flow.
- **Checks:** Each node accepts a fixture and returns only owned fields; visualization matches intended paths.
- **Tests:** Node contract, missing field, partial update merge, every entry/exit path.
- **Escalate when:** State must survive process boundaries or human pause.
- **Simplify when:** The graph has one trivial node or passes one value through wrappers.
- **Source:** `2.1`, state/node/edge examples, partial updates, `START`/`END`, compile and Mermaid visualization.

## Pattern: route with semantic decisions

- **Problem:** Conditional control is coupled to framework node names or fragile free text.
- **Use when:** A deterministic rule or structured model output selects a path.
- **Do not use when:** The next step is always fixed.
- **Signals:** Relevance, knowledge source, safety, or specialist classification.
- **Minimum design:** Structured decision enum → pure route function → explicit label-to-node map → default safe terminal.
- **Lecture tips:** Return labels such as `relevant`/`irrelevant` and map them separately; add a pass-through node only when it improves readability.
- **Comments:** Explain classification semantics, default path, and why model judgment is necessary.
- **Failure modes:** Typos such as inconsistent “irrelevant” labels; returning raw prose; router performs side effects.
- **Checks:** Enum and edge map agree; unknown output fails closed; all labels have tests.
- **Tests:** One fixture per label, malformed model output, timeout, low confidence, unknown label.
- **Escalate when:** Route history or replay becomes a product requirement.
- **Simplify when:** A deterministic predicate replaces the model router at equal quality.
- **Source:** `2.4` semantic relevance routes; `2.5` corrective route labels; `2.6` source router.

## Pattern: bound every cycle

- **Problem:** Rewrite, generation, tool, or supervisor loops can run indefinitely.
- **Use when:** A retry can repair a known transient or quality failure.
- **Do not use when:** Repeating the same inputs cannot change the result.
- **Signals:** Cyclic edges, tool-return-to-agent, regenerate, rewrite, or supervisor handoff.
- **Minimum design:** Attempt counters + per-stage and total budgets + changed input requirement + explicit exhausted terminal.
- **Lecture tips:** Corrected Agentic RAG must route rewrite back to retrieval; Self-RAG loops need production stop budgets; tool loops inspect the last AI message.
- **Comments:** State retry rationale, maximum, what changes between attempts, and exhausted behavior.
- **Failure modes:** Infinite cost; identical retries; a loop counter not persisted; success label never reached.
- **Checks:** Static review finds every back edge; runtime trace exposes counts and terminal reason.
- **Tests:** Immediate success, recovery on retry, repeated identical failure, malformed route, exact maximum.
- **Escalate when:** Human review is the only safe recovery after exhaustion.
- **Simplify when:** One fallback or immediate abstention performs as well.
- **Source:** `2.3` rewrite loop; `2.4` regeneration/rewrite loops; `3.3` agent-tool cycle; `3.7` supervisor loop.

## Pattern: parallelize independent work

- **Problem:** Independent retrievals or specialist tasks add latency when run sequentially.
- **Use when:** Branches share an input but have no ordering dependency.
- **Do not use when:** They write the same state field, rate limits dominate, or one result determines whether others are needed.
- **Signals:** Fan-out from one node and a join that requires named outputs.
- **Minimum design:** Shared immutable input → disjoint branch fields → timeout-aware fan-out → deterministic join.
- **Lecture tips:** Give each parallel node a distinct state key; keep deterministic calculations outside model prompts; separate current web data from local corpus evidence.
- **Comments:** Explain independence, join prerequisites, partial-failure policy, and concurrency limit.
- **Failure modes:** Last-write wins; duplicated external calls; one slow branch blocks indefinitely; merge order changes output.
- **Checks:** Branches do not depend on sibling output; join validates required fields and provenance.
- **Tests:** All succeed, each branch fails, timeout, partial result, deterministic join ordering.
- **Escalate when:** A queue or durable workflow engine is needed for long-running work.
- **Simplify when:** Conditional execution avoids most calls or measured latency gain is negligible.
- **Source:** `2.7`, parallel real-estate retrieval/calculation nodes, fan-out edges, and analyst join.

## Pattern: compose subgraphs deliberately

- **Problem:** A tested workflow must be reused as one stage of a larger flow.
- **Use when:** The child has a coherent contract and lifecycle.
- **Do not use when:** Reuse is only a shared helper function or prompt.
- **Signals:** Distinct input/output schema, independent tests, optional per-thread memory.
- **Minimum design:** Parent adapter → narrow child input → compiled subgraph → normalized child output → parent-owned route.
- **Lecture tips:** A compiled graph can be a node; keep the parent’s routing responsibility visible.
- **Comments:** Mark schema translation, state ownership, persistence mode, and failure propagation.
- **Failure modes:** Parent and child silently share fields; nested traces become unreadable; per-thread state leaks across calls.
- **Checks:** Child runs alone; parent-child adapter validates both directions; checkpoint choice is intentional.
- **Tests:** Direct child test, parent integration, child error, repeated thread, concurrent invocations.
- **Escalate when:** The child requires an independently deployed or permissioned boundary.
- **Simplify when:** A function call expresses the same contract.
- **Source:** `2.6`, compiled RAG graph used as a node and adaptive routing example. Current persistence choices: https://docs.langchain.com/oss/python/langgraph/use-subgraphs

## Pattern: stream for diagnosis

- **Problem:** Final output hides where retrieval, routing, tool use, or generation first failed.
- **Use when:** Intermediate state or model/tool events are useful to operators or UI users.
- **Do not use when:** Streaming exposes sensitive data or adds no actionable signal.
- **Signals:** Need token display, progress steps, route decisions, or earliest-divergence debugging.
- **Minimum design:** Select stream mode intentionally → normalize events → redact sensitive fields → log stable IDs → handle cancellation.
- **Lecture tips:** Stream graph values to observe tool loops; Streamlit callbacks can surface generation, but session context must be handled explicitly.
- **Comments:** Explain which events are user-visible, which are diagnostic, and what is redacted.
- **Failure modes:** Treating event shape as version-stable; exposing prompts/secrets; blocking UI on one slow node.
- **Checks:** Event consumer tolerates unknown events; final state equals non-streaming execution.
- **Tests:** Normal stream, tool events, error event, cancellation, empty output, redaction.
- **Escalate when:** Central trace retention and evaluation need a platform such as LangSmith.
- **Simplify when:** Named stage logs and final response satisfy operations.
- **Source:** `3.3` `stream(..., stream_mode="values")`; `chat_stream.py` callback/event handling. Verify target-version streaming API: https://docs.langchain.com/oss/python/langgraph/streaming

