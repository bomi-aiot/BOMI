# Code Comment Policy

> **Repository precedence (BOMI / S15P11E102).** The project authority for comment style
> is `CLAUDE.md` §21 (and §2). Where this generic policy and §21 differ, **§21 wins**:
> - Follow §21's Korean-section docstrings (`무엇을 하는가` / `누가 호출하는가` /
>   `무엇을 호출하는가` / `반환값` / `주의사항`, plus `왜 존재하는가` when non-obvious).
>   The `WHY / INVARIANT / FAILURE / SAFETY / REPLACE / OBSERVE` tags below are **optional**
>   inline aids; they do not replace those docstring sections.
> - The "no lessons / no lecture-style" prohibition is **relaxed** here. §2 mandates
>   teaching an inexperienced Korean team: introduce a library concept (embedding,
>   retriever, graph node, checkpointer) in one or two Korean lines on first use. That is a
>   required deliverable, not prohibited tutorial prose.
>
> Everything else below is compatible with §21 and still applies.

Use Korean comments to transfer decision context while Codex implements. Comments must help the next maintainer change the code safely.

## Allowed comment types

### `WHY`

Explain a non-obvious design choice and rejected simpler option.

```python
# WHY: 이 질문군은 표의 행 관계가 핵심이라 Markdown 구조를 보존한 청크를 사용한다.
```

### `INVARIANT`

State a contract that must remain true across refactors.

```python
# INVARIANT: 각 병렬 노드는 자기 상태 필드만 갱신해야 병합 순서에 영향을 받지 않는다.
```

### `FAILURE`

Name the real failure a guard prevents.

```python
# FAILURE: 동일 질의로 재시도하면 비용만 증가하므로 재작성 결과가 바뀌지 않으면 즉시 종료한다.
```

### `SAFETY`

Mark authorization, approval, privacy, replay, or side-effect boundaries.

```python
# SAFETY: 재개 시 이 노드가 다시 실행될 수 있으므로 승인 전에는 외부 변경을 수행하지 않는다.
```

### `REPLACE`

Identify an environment-specific seam and the contract a replacement must preserve.

```python
# REPLACE: 운영에서는 내구성 checkpointer로 교체하되 tenant 기반 thread 격리를 유지한다.
```

### `OBSERVE`

Explain a metric or trace field required to diagnose the earliest divergence.

```python
# OBSERVE: route_reason과 attempt를 함께 남겨 품질 실패와 예산 종료를 구분한다.
```

## Placement rules

- Place a comment immediately before the decision or boundary it explains.
- Comment graph state ownership, route semantics, loop budgets, join prerequisites, and terminal reasons.
- Comment RAG structure assumptions, knowledge boundary, abstention, provenance, and tuned retrieval parameters.
- Comment tool permission, call budget, result contract, first side effect, and idempotency.
- Comment thread ownership, retention, summary invariant, interrupt replay, and approval payload.
- Comment MCP process/network trust, initialization lifecycle, credentials, and transport choice.
- Comment evaluator intent, dataset version, threshold, and blind spots.
- Prefer one precise comment over a block that narrates implementation steps.

## Prohibited comments

- Do not explain obvious syntax or restate the next line.
- Do not turn source files into lessons, quizzes, or notebook summaries.
- Do not include secrets, personal data, full prompts, or production payloads.
- Do not claim a number is “optimal”; name the evaluation that justified it.
- Do not preserve stale framework notes after an API migration.
- Do not leave a deferred-work marker without owner, trigger condition, and safe current behavior.
- Do not hide a missing safety control behind a comment; implement the guard or fail closed.

## Review checklist

- Would deletion of this comment make a risky refactor more likely?
- Does it explain intent, invariant, failure, replacement, safety, or observation?
- Does the code enforce what the comment claims?
- Is the comment still correct for the installed dependency version?
- Is the Korean concise enough to scan during implementation?
- Does it avoid lecture-style line-by-line explanation?

## Source

Derived from decision-boundary comments and warnings across the mandatory notebooks and Python examples, especially table preservation (`2.2`), routing/loops (`2.3`–`2.5`), parallel state ownership (`2.7`), tool schemas (`3.2`–`3.4`), memory/HITL (`3.5`–`3.6`), supervisor control (`3.7`), UI thread handling (`chat.py`, `chat_stream.py`), and MCP lifecycle/security (`5.2`, `5.3`, MCP server files).
