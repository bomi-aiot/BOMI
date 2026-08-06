# Evaluation and Debugging

Prove behavior with fixed examples before trusting demos or architecture. The lecture sources provide graph inspection, streaming, and failure observations; they do not provide a complete LangSmith dataset/evaluation workflow. The LangSmith cards below are production hardening based on current official documentation.

## Contents

- Establish an evaluation slice
- Evaluate retrieval before generation
- Evaluate routes and budgets
- Debug the earliest divergence
- Run offline LangSmith experiments
- Add online feedback carefully
- Guard framework-version boundaries

## Pattern: establish an evaluation slice

- **Problem:** Architecture changes are judged by memorable demos rather than repeatable evidence.
- **Use when:** Any LLM, RAG, tool, or graph behavior changes.
- **Do not use when:** Never; at minimum keep deterministic fixtures.
- **Signals:** Prompt tuning, model swap, chunk change, new route/tool, regression report.
- **Minimum design:** Versioned input + expected invariants + permitted variability + quality/latency/cost/safety measures.
- **Lecture tips:** Reproduce the observed failure before adding the lecture’s next pattern.
- **Comments:** Mark why a fixture represents a user risk and which invariant it protects.
- **Failure modes:** One happy-path example; changing dataset and code together; scoring only final prose.
- **Checks:** Baseline and candidate use the same inputs and configuration; failures are inspectable.
- **Tests:** Answerable, no-answer, malformed, timeout, forbidden action, budget exhaustion.
- **Escalate when:** Human rubric or production sampling is needed.
- **Simplify when:** Remove examples that duplicate the same behavior boundary.
- **Source:** Derived from the staged failures across `2.2`–`2.5`, appendix summarization failure, and compiled/streamed inspections.

## Pattern: evaluate retrieval before generation

- **Problem:** A bad answer may originate in extraction, chunking, indexing, retrieval, or generation.
- **Use when:** The feature uses any external evidence.
- **Do not use when:** No retrieval exists.
- **Signals:** Unsupported answers, missing table facts, irrelevant top-k, conflicting evidence.
- **Minimum design:** Query set with relevant source/chunk expectations → retrieval metrics/inspection → grounded answer checks.
- **Lecture tips:** Compare raw Markdown with loader output; inspect similarity results before modifying prompts; preserve source metadata.
- **Comments:** Explain relevance labels, top-k choice, and corpus-version assumption.
- **Failure modes:** Model grader masks missing evidence; chunk IDs drift; index not rebuilt after preprocessing.
- **Checks:** Corpus/index version is recorded; top candidates and sources are stored with experiment results.
- **Tests:** Exact match, paraphrase, table fact, multi-chunk synthesis, no match, stale index.
- **Escalate when:** Reranking or human relevance labels are required.
- **Simplify when:** Direct structured lookup outperforms vector retrieval.
- **Source:** `2.2` preprocessing/retrieval cells; `2.3`/`2.4` relevance graders.

## Pattern: evaluate routes and budgets

- **Problem:** Aggregate answer score hides incorrect routes, retries, or tool usage.
- **Use when:** A graph branches or cycles.
- **Do not use when:** The path is truly linear.
- **Signals:** Conditional edges, rewrite/regenerate, tool loop, supervisor handoff.
- **Minimum design:** Expected route/terminal reason + maximum calls + latency/cost envelope + final-quality assertion.
- **Lecture tips:** Test semantic labels independently; render graph topology; observe streamed state after each step.
- **Comments:** State the route invariant and why its call budget is acceptable.
- **Failure modes:** Correct answer via forbidden path; retry count omitted; typoed route untested.
- **Checks:** Trace records route labels, calls, attempts, and terminal reason.
- **Tests:** Every branch, malformed label, recovery retry, identical retry, exact maximum, timeout.
- **Escalate when:** Policy or safety routes need independent validators.
- **Simplify when:** A rule-based route matches labeled examples.
- **Source:** `2.1` visualization; `2.4` semantic routers; `3.3` streamed tool loop; `3.7` supervisor.

## Pattern: debug the earliest divergence

- **Problem:** The final output is wrong but later nodes merely propagate the first error.
- **Use when:** A multi-stage run fails or regresses.
- **Do not use when:** A deterministic exception already identifies the defect.
- **Signals:** Trace/state stream differs from expected execution.
- **Minimum design:** Reproduce with fixed IDs → compare baseline/candidate stepwise → find first divergent state/message/tool call → fix that boundary.
- **Lecture tips:** Inspect compiled topology and stream values; keep query, evidence, grades, tool messages, and answer distinguishable.
- **Comments:** Add a comment only if the root cause is a durable invariant, not a one-off debugging note.
- **Failure modes:** Prompt-tuning the final node; changing several stages at once; logging secrets/raw sensitive content.
- **Checks:** Fix removes the earliest divergence and preserves other fixtures.
- **Tests:** Root-cause fixture plus adjacent success/failure cases.
- **Escalate when:** Provider/model nondeterminism needs repeated trials or statistical comparison.
- **Simplify when:** Replace an unstable model decision with deterministic code.
- **Source:** `2.1` compiled visualization; `3.3` state streaming; `chat_stream.py` event handling.

## Pattern: run offline LangSmith experiments

- **Problem:** Candidate prompts, models, retrievers, or workflows need repeatable comparison.
- **Use when:** A curated dataset and intentional credentials/cost are available.
- **Do not use when:** Dataset identity, evaluator contract, or data-governance approval is missing.
- **Signals:** Regression gate, model migration, retrieval tuning, release decision.
- **Minimum design:** Versioned dataset → target function → deterministic and/or rubric evaluators → named experiment → analyze failures and metrics.
- **Lecture tips:** Do not infer this workflow from saved notebook output; add it as an explicit production layer.
- **Comments:** Explain evaluator intent, acceptable threshold, dataset version, and known blind spots.
- **Failure modes:** LLM judge as sole authority; data leakage; comparing different dataset versions; no cost/latency fields.
- **Checks:** Experiment metadata identifies code/config/dataset; evaluator errors are separate from target failures.
- **Tests:** Evaluator unit fixtures, known pass/fail examples, missing output, repeated-trial variance.
- **Escalate when:** Human annotation or domain adjudication is required.
- **Simplify when:** Deterministic assertions fully capture the behavior.
- **Source:** Production hardening; not directly implemented in the mandatory lecture files. Current workflow: https://docs.langchain.com/langsmith/evaluation

## Pattern: add online feedback carefully

- **Problem:** Offline examples miss production inputs and operational failures.
- **Use when:** Sampling, privacy, retention, and alert ownership are defined.
- **Do not use when:** Raw sensitive content cannot be traced safely.
- **Signals:** Production drift, recurring abstention, tool failures, user feedback.
- **Minimum design:** Redacted trace → sampled evaluator/feedback → alert or review queue → curated offline example → regression test.
- **Lecture tips:** Keep diagnostic streaming separate from user-visible output and never copy notebook traces as proof.
- **Comments:** Mark sampling, redaction, retention, and feedback-to-dataset rules.
- **Failure modes:** Evaluator triggers a side effect; feedback silently changes prompts; unreviewed PII retention.
- **Checks:** Online findings become versioned offline cases before code changes.
- **Tests:** Sampling, redaction, evaluator outage, duplicate feedback, alert threshold.
- **Escalate when:** Compliance or incident response requires a governed observability pipeline.
- **Simplify when:** Aggregate operational counters are sufficient.
- **Source:** Production hardening based on lecture streaming/UI boundaries. Current evaluation model: https://docs.langchain.com/langsmith/evaluation

## Pattern: guard framework-version boundaries

- **Problem:** Code copies APIs from incompatible LangChain/LangGraph generations.
- **Use when:** Applying any lecture snippet to another repository.
- **Do not use when:** Never assume versions are compatible without inspection.
- **Signals:** `requirements.txt` and `pyproject.toml` disagree; deprecated constructors/parameters; import failures.
- **Minimum design:** Inspect lockfile/direct dependencies → identify target API generation → verify official docs → adapt one vertical slice → run import and focused tests.
- **Lecture tips:** The source includes older and newer dependency sets and notes API changes such as agent prompt configuration.
- **Comments:** Explain only unavoidable compatibility adapters and their removal condition.
- **Failure modes:** Mixing tutorial-era APIs; mass upgrades to fit a snippet; relying on transitive packages.
- **Checks:** Imports resolve from the target environment; new dependencies are direct and justified; lockfile is consistent.
- **Tests:** Clean install/import, focused execution, serialization/checkpoint compatibility where applicable.
- **Escalate when:** A framework migration needs its own scoped change and regression plan.
- **Simplify when:** Adapt the pattern concept to existing APIs rather than copying code.
- **Source:** `requirements.txt`, `pyproject.toml`, and appendix API-change note.

