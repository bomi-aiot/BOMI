# Tools, Memory, and HITL

Treat tool execution, conversation state, and human approval as separate boundaries. Combining them in one agent loop does not remove their distinct safety contracts.

## Contents

- Define reliable tools
- Preserve the tool-message protocol
- Separate read and write capabilities
- Add thread-scoped persistence
- Summarize conversation deliberately
- Interrupt before external effects
- Integrate UI sessions safely

## Pattern: define reliable tools

- **Problem:** The model chooses the wrong tool or produces unusable arguments.
- **Use when:** A capability must be selected or parameterized from natural language.
- **Do not use when:** A deterministic function call is already known.
- **Signals:** Multiple capabilities, stable typed arguments, meaningful model choice.
- **Minimum design:** Specific name + action-focused docstring + typed narrow args + validated result/error schema.
- **Lecture tips:** `@tool` metadata directly shapes model choice; inspect built-in integrations before maintaining a custom wrapper.
- **Comments:** Explain non-obvious constraints, permissions, and why a parameter is model-visible.
- **Failure modes:** Generic names; hidden required context; huge string results; exceptions leaking internals.
- **Checks:** Schema matches implementation; description distinguishes nearby tools; output is bounded.
- **Tests:** Valid args, missing/extra args, invalid enum, timeout, provider error, large result.
- **Escalate when:** Context/state injection or a remote tool boundary is required.
- **Simplify when:** The caller can invoke the function directly.
- **Source:** `3.2` custom tools and binding; `3.4` built-in/retriever tools; `3.8` tool naming/docstrings/arguments.

## Pattern: preserve the tool-message protocol

- **Problem:** Tool results are not associated with the model’s requested calls.
- **Use when:** Implementing a tool loop manually or testing framework behavior.
- **Do not use when:** A verified higher-level agent already owns the protocol and no customization is needed.
- **Signals:** `AIMessage.tool_calls`, `ToolMessage`, or `ToolNode`.
- **Minimum design:** Human message → AI tool request → one result per call ID → AI continuation → terminal output.
- **Lecture tips:** `ToolNode` expects an AI message with tool calls and returns tool messages; route from the last AI message.
- **Comments:** Mark correlation-ID and ordering invariants.
- **Failure modes:** Missing tool result; wrong call ID; result inserted before request; infinite agent-tool cycling.
- **Checks:** Every requested call receives exactly one normalized result; ordering survives persistence.
- **Tests:** Zero, one, and multiple calls; one call error; out-of-order result; loop budget.
- **Escalate when:** Approval or durable resume must occur between request and execution.
- **Simplify when:** One direct tool call is predetermined.
- **Source:** `3.2` manual message sequence; `3.3` `ToolNode`, `MessagesState`, and `tools_condition`.

## Pattern: separate read and write capabilities

- **Problem:** An agent can create side effects while answering, previewing, or debugging.
- **Use when:** Tools touch email, source control, tickets, databases, or other external systems.
- **Do not use when:** The operation is pure and local.
- **Signals:** OAuth scopes, mutations, irreversible actions, tenant/user ownership.
- **Minimum design:** Read allowlist → plan/preview → server-side authorization → explicit approval → idempotent write → audit record.
- **Lecture tips:** Prefer existing tools but narrow their scope; the lecture Gmail and GitHub examples demonstrate capability, not production permission policy.
- **Comments:** Label the first side-effect line, approval precondition, idempotency key, and audit identity.
- **Failure modes:** Broad OAuth scope; model-selected tenant; duplicate writes on retry; write during explanation.
- **Checks:** Approval cannot be forged in prompt text; denied tools fail closed; read-only mode is testable.
- **Tests:** Allowed read, denied write, valid approval, stale approval, replayed write, wrong tenant.
- **Escalate when:** A human or policy service must approve the exact action payload.
- **Simplify when:** Remove the write tool and return a copy-ready proposal.
- **Source:** `3.4` Gmail scope example; `5.3` GitHub MCP PR-comment action.

## Pattern: add thread-scoped persistence

- **Problem:** A workflow must resume or retain conversation state across invocations.
- **Use when:** Product behavior names a conversation/thread lifecycle, fault recovery, or HITL pause.
- **Do not use when:** Each request is stateless or history can be reconstructed cheaply.
- **Signals:** `thread_id`, checkpointer, resume, time travel, multi-turn context.
- **Minimum design:** Stable tenant-bound thread ID + selected checkpointer + state schema/version + retention/deletion policy.
- **Lecture tips:** Pass `thread_id` in runtime configuration; in-memory savers are for local examples, not durable production storage.
- **Comments:** Explain thread derivation, ownership, retention, and migration expectations.
- **Failure modes:** Fixed shared thread ID; cross-user leakage; treating checkpoint history as the business database.
- **Checks:** Two users cannot read each other’s state; restart behavior matches the chosen store.
- **Tests:** Same-thread continuation, different-thread isolation, restart, missing thread, schema migration.
- **Escalate when:** Durable database-backed checkpointing and operational cleanup are required.
- **Simplify when:** Persist only the final domain record and reconstruct transient graph state.
- **Source:** `3.5` `MemorySaver` and thread config; `chat.py`/`chat_stream.py` fixed `"1234"` thread risk. Current model: https://docs.langchain.com/oss/python/langgraph/persistence

## Pattern: summarize conversation deliberately

- **Problem:** Long message history exceeds context or distracts the model.
- **Use when:** Multi-turn quality tests show history growth is harmful or costly.
- **Do not use when:** Short sessions fit comfortably and exact history is required.
- **Signals:** Token growth, lost older facts, latency/cost increase.
- **Minimum design:** Explicit summary field → summary prompt with existing summary → retain recent raw messages → remove older messages by ID.
- **Lecture tips:** Extend message state with `summary`; include summary as system context; keep a tuned recent-message window.
- **Comments:** State what the summary must preserve, what can be dropped, and trigger threshold.
- **Failure modes:** Summary drifts; deletion occurs before successful summary; sensitive facts persist indefinitely.
- **Checks:** Critical facts survive compaction; removed messages are intentional; summary is inspectable.
- **Tests:** First summary, incremental summary, short history, failed summarization, privacy deletion.
- **Escalate when:** Long-term semantic memory needs a separately governed store.
- **Simplify when:** Deterministic structured fields replace free-form history.
- **Source:** `3.5`, extended message state, summary node, system-message injection, and `RemoveMessage`.

## Pattern: interrupt before external effects

- **Problem:** A risky action needs human review and resumable execution.
- **Use when:** Approval must bind to an exact proposed payload.
- **Do not use when:** The action is forbidden or can be made read-only.
- **Signals:** `interrupt`, `Command`, approval/edit/reject choices, checkpointer.
- **Minimum design:** Prepare pure proposal → interrupt with JSON-serializable payload → resume with typed decision → revalidate → idempotent effect.
- **Lecture tips:** Checkpointer and thread are required; route with `Command`; a node can re-execute before reaching the interrupt.
- **Comments:** Place a Korean `SAFETY` comment before the effect explaining approval and replay invariants.
- **Failure modes:** Side effect before interrupt; catching or reordering interrupts; stale approval; duplicate effect after resume.
- **Checks:** Nothing external changes before approval; resumed payload is reauthorized; effect has an idempotency key.
- **Tests:** Approve, edit, reject, invalid resume, stale data, duplicate resume, process restart.
- **Escalate when:** Approval requires external identity, signatures, or multi-party policy.
- **Simplify when:** Return the proposal and let a separate trusted system execute it.
- **Source:** `3.6`, `interrupt`, edit/reject routing with `Command`, checkpointed resume. Current rules: https://docs.langchain.com/oss/python/langgraph/interrupts

## Pattern: integrate UI sessions safely

- **Problem:** UI message state, graph state, streaming callbacks, and errors become inconsistent.
- **Use when:** A chat UI invokes a persistent or streaming graph.
- **Do not use when:** A synchronous API boundary is sufficient.
- **Signals:** Streamlit session state, callbacks, graph state lookup, reruns.
- **Minimum design:** Per-user/thread session ID → normalized UI history → graph invocation → safe streamed events → user-safe error + internal log.
- **Lecture tips:** Retrieve graph state by thread config; preserve callback context where UI frameworks require it.
- **Comments:** Explain session/thread mapping, event normalization, and redaction boundary.
- **Failure modes:** Hardcoded thread ID; raw exception shown to users; callback runs without session context; duplicate rendering.
- **Checks:** Concurrent users remain isolated; UI and checkpoint agree after rerun.
- **Tests:** New/returning session, concurrent sessions, stream cancellation, provider error, reconnect.
- **Escalate when:** Authentication and durable session ownership must move to a backend.
- **Simplify when:** Keep the UI stateless and let a service own the thread.
- **Source:** `chat.py` state lookup and invocation; `chat_stream.py` callbacks and session-context wrapper.

