# Multi-Agent and MCP

Add a specialist or protocol boundary only when it creates measurable isolation, reuse, or ownership value.

## Contents

- Route to specialist subgraphs
- Bound supervisor-worker systems
- Expose a stable MCP capability
- Choose and secure MCP transport
- Consume MCP tools safely

## Pattern: route to specialist subgraphs

- **Problem:** Requests need materially different knowledge paths or execution policies.
- **Use when:** Specialists have distinct state, context, tools, permissions, or owners.
- **Do not use when:** Only the system prompt differs.
- **Signals:** A small structured router can select one independently testable subgraph.
- **Minimum design:** Typed intent → label-to-specialist map → narrow child input/output → common final response contract.
- **Lecture tips:** Route directly to compiled specialist graphs; use a small model for routing/basic answers when evaluation supports it.
- **Comments:** Explain specialist boundary, fallback route, and output normalization.
- **Failure modes:** Router ambiguity; duplicated retrieval; incompatible state; context copied to every worker.
- **Checks:** Each specialist runs alone; router confusion matrix is measured; unknown intent fails safely.
- **Tests:** One case per specialist, ambiguous request, out-of-domain request, child failure.
- **Escalate when:** Several specialists must collaborate on the same request.
- **Simplify when:** Namespaced tools in one bounded agent perform equally well.
- **Source:** `2.6` adaptive subgraph routing; `2.8` RouteLLM and specialist graphs.

## Pattern: bound supervisor-worker systems

- **Problem:** Several specialists must contribute before a final synthesis.
- **Use when:** Workers own different facts or capabilities and collaboration improves a fixed evaluation set.
- **Do not use when:** Tasks are a fixed parallel workflow or one worker can answer.
- **Signals:** Explicit supervisor decision, labeled worker response, deterministic handoff schema.
- **Minimum design:** Supervisor with remaining budget → selected worker → source-labeled result → supervisor or final analyst → terminal reason.
- **Lecture tips:** Workers should report facts back to the supervisor; reserve final synthesis for an analyst; keep external adapters outside agent prompts.
- **Comments:** Mark handoff schema, remaining-call budget, worker permissions, and conflict policy.
- **Failure modes:** Endless delegation; workers ask each other; context explosion; unsourced synthesis; import-time API calls.
- **Checks:** Supervisor stops; workers cannot access unrelated tools; all claims retain worker/source attribution.
- **Tests:** Single worker, multiple workers, wrong worker, conflict, worker timeout, maximum handoffs.
- **Escalate when:** Workers require separate deployment, credentials, or cross-language reuse.
- **Simplify when:** Fan-out/fan-in nodes express the same known collaboration.
- **Source:** `3.7` trading supervisor/workers/analyst; `trading_graph.py` external adapters; `2.7` fixed parallel alternative.

## Pattern: expose a stable MCP capability

- **Problem:** A tool or prompt must be reused across processes, repositories, or languages.
- **Use when:** The remote ownership and protocol boundary are intentional.
- **Do not use when:** A local function is sufficient or the interface changes rapidly inside one codebase.
- **Signals:** Independent server lifecycle, stable typed schema, explicit authentication and versioning.
- **Minimum design:** Lazy resource initialization → narrow FastMCP tool/prompt → typed errors → health/logging → direct client contract test.
- **Lecture tips:** Tool names, docstrings, and arguments remain model-facing; test the server directly before connecting an agent.
- **Comments:** Mark lifecycle ownership, expensive initialization, version contract, and secret source.
- **Failure modes:** Model/vector index initialized at import; credentials embedded in code; huge opaque responses.
- **Checks:** Import has no network side effect; server starts without optional data; direct roundtrip returns bounded output.
- **Tests:** Schema discovery, valid call, invalid args, dependency unavailable, timeout, shutdown.
- **Escalate when:** Multi-tenant auth, rate limiting, or durable jobs are required.
- **Simplify when:** Keep the capability as a package-level function.
- **Source:** `5.2 커스텀 MCP 서버 개발방법.py`, `mcp_stdio_server.py`, and `mcp_sse_server.py`.

## Pattern: choose and secure MCP transport

- **Problem:** A client must connect to a local subprocess or remote MCP service safely.
- **Use when:** MCP is already justified as the capability boundary.
- **Do not use when:** Transport complexity outweighs reuse.
- **Signals:** STDIO command configuration or authenticated HTTP endpoint.
- **Minimum design:** Choose STDIO for owned local subprocesses or Streamable HTTP for remote services → authenticate → bound timeouts → log protocol events safely.
- **Lecture tips:** The lecture demonstrates STDIO and legacy SSE; verify current spec because Streamable HTTP supersedes standalone HTTP+SSE.
- **Comments:** Explain trust boundary, credential injection, timeout, and deployment-specific configuration.
- **Failure modes:** Protocol data mixed with STDIO logs; unvalidated HTTP origin; public unauthenticated endpoint; copied legacy transport.
- **Checks:** STDOUT carries only protocol messages in STDIO; HTTP validates origin/auth; secrets come from environment.
- **Tests:** Start/connect/disconnect, malformed frame, unauthorized request, timeout, server restart.
- **Escalate when:** Network policy, secret rotation, or service identity needs platform ownership.
- **Simplify when:** Use the client library’s supported local transport without a custom proxy.
- **Source:** `5.2`/`mcp_stdio_server.py` STDIO, `mcp_sse_server.py` SSE, `5.3` client configurations. Current transport spec: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

## Pattern: consume MCP tools safely

- **Problem:** Discovered remote tools expand an agent’s authority dynamically.
- **Use when:** A trusted MCP server exposes an approved tool subset.
- **Do not use when:** The server/tool provenance or permissions are unknown.
- **Signals:** `MultiServerMCPClient`, discovered schemas, external credentials, possible writes.
- **Minimum design:** Pin server config → discover → filter allowlist → inspect schemas → direct-call smoke test → bounded agent → approval for writes.
- **Lecture tips:** The GitHub example loads selected toolsets and streams agent/tool events; a PR comment is a write and needs explicit approval.
- **Comments:** Mark server trust, allowlisted tool names, credential scope, and mutation approval.
- **Failure modes:** Trusting every discovered tool; leaking a PAT; Docker command drift; duplicate remote writes.
- **Checks:** Unknown tools are rejected; credential has least privilege; write payload is previewed and idempotent.
- **Tests:** Discovery, allowed read, filtered tool, auth failure, denied write, approved write, replay.
- **Escalate when:** Central policy must govern server/tool admission.
- **Simplify when:** Bind one local API client directly.
- **Source:** `5.3`, Streamable HTTP/STDIO clients, GitHub PAT environment use, Docker server config, and streamed tool execution.

