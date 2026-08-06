# Architecture Selection

Choose the smallest architecture that proves the requested behavior. Record the decision before adding framework layers.

## Decision record

Write down:

- User-visible behavior and one representative fixture
- Required knowledge, tools, side effects, and freshness
- Quality, p95 latency, cost, and safety limits
- Deterministic versus model-judged decisions
- Expected failure paths and terminal reasons
- Baseline architecture and evidence required to escalate

## Pattern: deterministic function or simple chain

- **Problem:** Transform known inputs or make one model decision.
- **Use when:** The steps and tool order never vary.
- **Do not use when:** Execution must pause, resume, branch, or recover per step.
- **Signals:** Stable schema, no external tool selection, one prompt-response boundary.
- **Minimum design:** Validate input → run pure code or one model call → validate output.
- **Lecture tips:** Keep calculations deterministic; small-model routing is useful only for genuinely semantic choices.
- **Comments:** Explain why a rule is deterministic and what must remain outside the prompt.
- **Failure modes:** Hiding business rules in prompts; adding graph state without a lifecycle need.
- **Checks:** Same input produces the same non-model fields; schema failures are explicit.
- **Tests:** Boundary values, malformed input, model timeout, output-schema rejection.
- **Escalate when:** A measured case needs branching, replay, or variable tool order.
- **Simplify when:** A graph has one path and no checkpoint, streaming, retry, or inspection value.
- **Source:** `2.6` routing/basic-LLM cells; `2.7` calculation nodes; `3.8` fixed workflow versus tool conversion.

## Pattern: 2-Step RAG

- **Problem:** Answer from a corpus that should always be searched first.
- **Use when:** Retrieval is mandatory and the generation path is fixed.
- **Do not use when:** No corpus is needed, or retrieval itself is optional and request-dependent.
- **Signals:** Stable corpus boundary, inspectable evidence, one retrieval followed by one answer.
- **Minimum design:** Normalize query → retrieve top candidates → build cited context → answer or abstain.
- **Lecture tips:** Preserve document structure; begin with a small `k`; inspect retrieved chunks before tuning the model.
- **Comments:** Mark the chunking assumption, abstention rule, and replaceable retrieval configuration.
- **Failure modes:** Stuffing all documents into context; broken tables; answering when evidence is absent.
- **Checks:** Evidence supports the answer; empty retrieval cannot become a confident answer.
- **Tests:** Known answer, no answer, ambiguous query, malformed document, stale index.
- **Escalate when:** Measured failures require rewrite, relevance gates, or external fallback.
- **Simplify when:** The data already exists behind a precise database/API query.
- **Source:** `2.2` PDF preprocessing, splitting, vector store, and sequential RAG cells; appendix direct-answer prompt.

## Pattern: fixed LangGraph workflow

- **Problem:** Make explicit stages, routes, parallel work, retries, streaming, or resumability observable.
- **Use when:** The orchestration is known but has meaningful state transitions.
- **Do not use when:** A linear function or chain remains easier to test and operate.
- **Signals:** Typed shared state, named terminal outcomes, independent branches, checkpoint requirement.
- **Minimum design:** Narrow state → pure route functions → single-purpose nodes → explicit `START`/`END` → compiled inspection.
- **Lecture tips:** Return partial state updates; use semantic route labels; render the graph before trusting execution.
- **Comments:** Explain route invariants, join requirements, loop budgets, and replay boundaries.
- **Failure modes:** Nodes mutating unrelated fields; typo-prone labels; unbounded regeneration; hidden side effects.
- **Checks:** Every route reaches a terminal state within budget; parallel writers do not collide.
- **Tests:** Each node, each route, maximum loop, join failure, resume after checkpoint.
- **Escalate when:** Tool choice or order truly varies with the request.
- **Simplify when:** Only one route is used in evaluation or the graph merely wraps a chain.
- **Source:** `2.1` graph primitives; `2.4` semantic routers; `2.6` subgraphs; `2.7` parallel nodes.

## Pattern: bounded tool agent

- **Problem:** Let a model choose among read tools or vary their order.
- **Use when:** Intent cannot be mapped reliably to one fixed workflow and tools have clear schemas.
- **Do not use when:** The action is deterministic, permission-sensitive writes lack approval, or a fixed route is sufficient.
- **Signals:** Multiple safe capabilities, observable tool calls, strict iteration and cost budgets.
- **Minimum design:** Allowlisted tools → tool-calling model → validated call → result message → bounded decision loop.
- **Lecture tips:** Tool name, docstring, argument types, and result shape influence selection; preserve message order.
- **Comments:** State why model choice is allowed, the call budget, and which actions remain forbidden.
- **Failure modes:** Hallucinated args; repeated calls; opaque tool errors; write action triggered during explanation.
- **Checks:** Invalid tools and args fail closed; terminal reason distinguishes success, refusal, and budget exhaustion.
- **Tests:** No-tool answer, one tool, multiple tools, malformed args, timeout, forbidden write, loop cap.
- **Escalate when:** Roles need different context, permissions, owners, or independent lifecycles.
- **Simplify when:** Evaluation shows one stable tool sequence.
- **Source:** `3.2` tool calls/messages; `3.3` `ToolNode` loop; `3.4` built-in tools; `3.8` custom tool contracts.

## Pattern: multi-agent boundary

- **Problem:** Coordinate specialists with materially different context, tools, permissions, or ownership.
- **Use when:** Isolation reduces prompt/tool interference or aligns separate operational owners.
- **Do not use when:** “Specialist” means only a different prompt over the same inputs and tools.
- **Signals:** Explicit handoff contract, bounded supervisor, per-role allowlists, measurable improvement over one agent.
- **Minimum design:** Router/supervisor → narrow worker inputs → labeled worker outputs → deterministic aggregation → stop budget.
- **Lecture tips:** Specialist subgraphs can be routed; workers should return facts to a supervisor; keep final synthesis separate.
- **Comments:** Explain the boundary, handoff schema, supervisor budget, and ownership of side effects.
- **Failure modes:** Supervisor loops; duplicated retrieval; context explosion; unclear source attribution.
- **Checks:** Each worker is independently testable; handoff preserves provenance; one failed worker has defined handling.
- **Tests:** Correct route, irrelevant specialist, partial failure, conflicting results, max handoffs.
- **Escalate when:** A remote capability must be separately deployed or shared through a stable protocol such as MCP.
- **Simplify when:** One agent with namespaced tools matches quality at lower latency and cost.
- **Source:** `2.8` RouteLLM/multi-agent examples; `3.7` supervisor-workers; `5.3` MCP-discovered tools.

