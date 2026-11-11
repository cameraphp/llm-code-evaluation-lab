# Plan: LLM Code Evaluation Lab

Independent portfolio lab. It evaluates **code behaviour** of controlled candidate
fixtures against explicit task contracts, using an evidence-backed scoring manifest,
severity gating, a failure taxonomy and reviewer feedback. No LLM is invoked; the
methodology is designed so it *could* be applied to generated code.

## Roadmap

| Stage | Scope | Status |
|---|---|---|
| 1 | Minimal evaluation core (registry, check runner, scorer, gating, canonical JSON + Markdown report, CLI) and Task 1: API-style idempotent order creation with `reference`, `flawed`, `partial` fixtures | Implemented (see `validation.md`) |
| 2 | Task 2: multi-tenant resource authorization. Task 3: agent-proposed background jobs with bounded retries and deduplication, using the same evaluator, scorer and report | Implemented (owner-authorized 2026-11-11; see `validation.md`) |
| 3 | Calibration across tasks, explicitly synthetic reviewer-agreement example, synthetic review demo, portfolio documentation | Implemented locally (owner-authorized 2026-11-11). Publication is a separate owner decision |

Each stage ends with a checkpoint and stops; the next stage needs a new owner instruction.

## Stage 1 design decisions

- **Trust boundary.** The CLI selects a task and a candidate ID from a source-code
  allowlist (`registry.py`). The CLI never accepts a path, code string, URL or
  module name. Every fixture file is pinned by SHA-256 (CRLF normalised to LF). A changed
  file is refused until someone reviews it and pins it again. Fixtures run in-process:
  **neither a subprocess nor a timeout is a sandbox**. Untrusted-code execution is deferred
  to a separately designed isolated runner.
- **Separation.** Fixtures live in `fixtures/` and the oracle, expected values and scoring
  manifest live in `src/code_eval_lab/`. Seeded-defect notes (`fixtures/.../DEFECTS.md`) are
  never read by the evaluator. Candidate module attributes (for example a self-assessed score)
  are ignored.
- **Storage.** SQLite files in per-check temporary directories give real transactions,
  `UNIQUE` constraints, multi-connection races and restart replay without a server.
- **Determinism.** Evidence records only stable values: statuses, counts, booleans, totals and
  fictional field values. It never records raw order IDs, timestamps, temp paths or wall time.
- **Scoring.** There are 90 automated points (40/30/20), and each check contributes at most
  once. ERROR or MISSING makes the evaluation INCOMPLETE with no aggregate. Critical failures
  block regardless of score. The 10 manual maintainability points stay PENDING in Stage 1.

## Stage 2 design decisions

- **Same rubric shape.** Each task has its own fixed manifest of 40/30/20 = 90 points, validated
  by the shared scorer. Checks map to categories by contract meaning. Critical checks cover tenant
  exposure, the permission gate, deduplication and retry bounds.
- **Task 2.** The harness supplies a trusted `identity(token)` lookup that returns an immutable
  principal. Request headers and params never carry authority. Authentication (401),
  function-level authorization (403), input validation (400) and object-level scoping (404,
  shared with nonexistent IDs) are separate steps.
- **Task 3.** The agent is a fixed synthetic proposal source. Effects are in-memory fakes that are
  atomic per call and deliberately not idempotent. Time comes from a fake clock. Persistence uses
  SQLite in a temp dir. Exactly-once external effects are explicitly **not** claimed.
- **Leak-safe evidence.** Evidence records sensitive *categories* and key names, never sensitive
  values. A non-vocabulary error reason is shown as withheld, so a report never repeats a leak.

## Stage 3 design decisions

- **Explicit review fields.** Reports carry `manual_score`, `review_source` (`none`,
  `synthetic_example` or `human`) and `total_score`. A synthetic annotation yields the verdict
  `SIMULATED_REVIEW`. Only a `human` review can yield `ACCEPTABLE`, and BLOCKED always wins.
- **Calibration outside scoring.** `calibration/expected-outcomes.json` holds the expected outcomes.
  It is compared after scoring and never read by the scorer or by candidates.
- **Agreement demo.** Stdlib exact fractions; undefined cases are reported as null; the input is six
  hand-crafted `synthetic_example` items.
- **Compact canonical sample.** The `evaluate-suite` output is copied into `reports/`, and a test
  detects drift. Full per-check evidence stays available through `evaluate`.

## Out of scope (all stages unless re-authorized)

No real LLM/API calls, Docker, cloud SDKs, database server, frontend, deployment, Git
init, publishing, licensing choice or arbitrary-code upload/run feature.
