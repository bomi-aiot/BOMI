---
name: apply-llm-project-patterns
description: Apply and verify production-minded LangChain, LangGraph, RAG, tool, memory, HITL, multi-agent, MCP, and LangSmith patterns in an existing project. Use when Codex must add, change, debug, evaluate, or harden an LLM feature, choose the least-complex architecture, improve retrieval, design tool calls, add persistence or approval, connect MCP, or diagnose traces. Do not use for a purely conceptual explanation or unrelated general Python work.
---

# Apply LLM Project Patterns

Implement the requested user behavior in the target repository. Treat the bundled references as decision support extracted from working lecture examples, not as a syllabus or code to copy blindly.

## Authority order (read first)

These references are **generic**. This repository has project-specific authority documents,
and when they disagree the project document wins:

1. `docs/database/mvp-erd.md` — authoritative for the database schema and vocabulary.
2. `CLAUDE.md` (repo root) — authoritative for the conversation runtime: when to speak,
   how to speak, safety timing, graph structure, comment standard (§21), and the LLM budget
   (§16). It overrides these references on every point they touch.
3. These `references/` files — everything the two documents above do not cover.

Concretely: comment style follows CLAUDE.md §21, not the tag list in
[code-comment-policy.md](references/code-comment-policy.md); graph and LLM-budget decisions
follow §6/§7/§16, not the fan-out and model-router defaults in
[graph-workflows.md](references/graph-workflows.md). Both files carry a precedence note.

## Operating contract

- Inspect the actual repository, dependency versions, tests, configuration, and entry points before proposing architecture.
- State the requested user behavior, success evidence, protected scope, and unknowns.
- Start with the least-complex viable structure and add graph or agent behavior only when a measured failure requires it.
- Reuse the repository's conventions and dependencies before adding or upgrading packages.
- Verify current framework APIs in official documentation before writing version-sensitive code.
- Keep secrets in environment or secret stores. Never copy credentials from examples.
- Separate deterministic business rules from model judgment.
- Preserve user changes and report checks that were not run.

## Workflow

### 1. Establish the baseline

1. Trace the current input-to-output path.
2. Identify the smallest user-visible behavior to implement.
3. Record quality, latency, cost, and safety acceptance criteria.
4. Create a deterministic fixture or evaluation example before changing architecture.
5. Report the intended files, contracts, risks, and verification commands.

### 2. Select the minimum sufficient architecture

Use this escalation order:

1. Plain Python function for deterministic transformations.
2. Simple chain for one model decision.
3. 2-Step RAG when retrieval always precedes generation.
4. Fixed LangGraph workflow for explicit stages, branching, parallel work, retries, or resumability.
5. Bounded tool agent when tool choice or order varies by request.
6. Multi-agent only when roles have genuinely different context, tools, permissions, or ownership.

Read [architecture-selection.md](references/architecture-selection.md) before choosing or changing the architecture. Do not escalate without a failing baseline and a comparison plan.

### 3. Load only relevant references

- For ingestion, chunking, retrieval, grounding, rewriting, or web fallback, read [rag-and-retrieval.md](references/rag-and-retrieval.md).
- For typed state, nodes, routes, loops, parallel execution, streaming, or subgraphs, read [graph-workflows.md](references/graph-workflows.md).
- For tool contracts, message ordering, conversation history, checkpointing, or approval, read [tools-memory-hitl.md](references/tools-memory-hitl.md).
- For routing across specialists, supervisor designs, or MCP boundaries, read [multi-agent-and-mcp.md](references/multi-agent-and-mcp.md).
- For tests, datasets, traces, graders, or regressions, read [evaluation-and-debugging.md](references/evaluation-and-debugging.md).
- Before adding instructional comments, read [code-comment-policy.md](references/code-comment-policy.md).
- When provenance or lecture coverage matters, read [source-map.md](references/source-map.md).

### 4. Implement in a vertical slice

1. Keep raw input, normalized input, retrieved evidence, decisions, actions, and final output distinguishable.
2. Make each node or tool return a narrow, testable contract.
3. Add timeouts, call budgets, loop budgets, and explicit terminal reasons.
4. Keep read operations separate from writes.
5. Place authorization and human approval before the first external side effect.
6. Make any operation that may replay after retry or resume idempotent.
7. Add concise Korean comments only at non-obvious decisions, invariants, failure boundaries, and replacement points.
8. Avoid line-by-line teaching comments and tutorial prose.

### 5. Verify behavior

Run the narrowest deterministic checks first, then broader or paid checks:

1. Unit-test pure transformations, routes, tool schemas, and stop conditions.
2. Test success, no-answer, malformed input, forbidden tool, timeout, and budget exhaustion paths.
3. For persistence or HITL, test interrupt, resume, and duplicate-effect prevention with the same thread.
4. For MCP, call the server directly before placing it behind an agent.
5. Compare the changed implementation with the baseline on the same dataset.
6. Inspect the earliest trace step that diverges from the expected path.
7. Run LangSmith evaluation only when credentials, dataset identity, and cost are intentionally configured.

### 6. Simplify and report

- Remove graph, agent, grader, memory, subgraph, MCP, or multi-agent layers that do not improve the acceptance evidence.
- Report changed files, behavior proved, measurements, commands run, failures, and unverified external paths.
- Do not claim production quality from notebook output, a single answer, graph compilation, or an LLM judge alone.

## Non-negotiable safety boundaries

- Never create an unbounded rewrite, regeneration, tool, or supervisor loop.
- Never let an LLM invent authorization, tenant identity, tool allowlists, or approval.
- Never execute a write tool as a by-product of explaining or previewing an action.
- Never place secrets, raw sensitive records, or oversized binary content in graph state, prompts, or traces.
- Never treat a checkpointer as a substitute for durable production storage design.
- Never force LangGraph, Agent, Multi-Agent, or MCP when a simpler local boundary is sufficient.
