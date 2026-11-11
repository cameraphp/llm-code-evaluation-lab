# llm-code-evaluation-lab

> This repository is an independent portfolio laboratory. It is not presented as paid RLHF,
> data-labeling or professional AI-training-company experience. It demonstrates methods for
> designing, testing and evaluating technical code submissions using controlled fixtures.

The lab defines programming tasks with explicit contracts. Trusted checks run against controlled
candidate implementations, and the results are scored with an evidence-backed, severity-gated rubric
that produces reviewer feedback. No LLM is called. The methodology *could* be applied to generated
code, but no model comparison was run.

## Three tasks

| Task | Probes | Contract |
|---|---|---|
| `task-01` | Idempotent order creation: replay, conflicting payload, race, restart, pre-commit failure | [TASK.md](examples/task-01-api-idempotency/TASK.md) |
| `task-02` | Multi-tenant reads: authentication vs authorization, BOLA/IDOR, collection scope, safe denials | [TASK.md](examples/task-02-tenant-authorization/TASK.md) |
| `task-03` | Synthetic agent job proposals: tool allowlist, dedup, retry bound and schedule, dead letter, restart | [TASK.md](examples/task-03-agent-jobs/TASK.md) |

Each task has a `reference`, a `flawed` and a `partial` fixture. See [TASK_SPEC.md](TASK_SPEC.md).

## Run it (Windows, Python 3.11+)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m code_eval_lab evaluate-suite        # all 9 candidates + demos
.\.venv\Scripts\python.exe -m code_eval_lab evaluate --task task-02 --candidate flawed
```

Other commands are `list` (allowlist and digest status) and `agreement` (the annotation-metric demo).
Output goes to the git-ignored `artifacts/` directory. A curated canonical sample is in
[reports/sample-evaluation.md](reports/sample-evaluation.md).

## Reference vs flawed evidence

| Task | reference | flawed | partial |
|---|---|---|---|
| task-01 | 90/90 REVIEW_PENDING | 52/90 **BLOCKED**: duplicate orders in race and after restart, changed payload replayed | 75/90 **BLOCKED**: quantity and price changes replay the earlier order |
| task-02 | 90/90 REVIEW_PENDING | 48/90 **BLOCKED**: cross-tenant read, client-chosen tenant, token in audit log | 80/90 **BLOCKED**: list skips the role check |
| task-03 | 90/90 REVIEW_PENDING | 26/90 **BLOCKED**: weak gate, upsert re-execution, off-by-one retries, stored error text | 82/90 CHANGES_REQUESTED: permanent errors retried (major, not critical) |

The suite reports **CALIBRATED** when every seeded defect is detected and every reference passes.

## How to read a score

- **90 automated points** (correctness 40, safety/integrity 30, resilience 20) plus **10 manual
  points** for maintainability.
- The **verdict is a gate, not a threshold**. One failed critical check means BLOCKED, whatever the
  number. ERROR or MISSING means INCOMPLETE, and no aggregate is published.
- A manual review is **pending**, so `manual_score` and `total_score` are `null`. Synthetic
  annotations show the arithmetic as `SIMULATED_REVIEW`, never as an approval.
- The full rules are in [RUBRIC.md](RUBRIC.md). The method and evidence kinds are in
  [EVALUATION_METHODOLOGY.md](EVALUATION_METHODOLOGY.md).

## Trusted-fixture boundary

Fixtures are allowlisted by ID, SHA-256 pinned and **imported in-process. This is not a sandbox.**
Only owner-reviewed code may be run. See [SECURITY.md](SECURITY.md).

## Provenance and review status

- **Fixtures, tests and docs:** written with AI assistance (Claude Code) and **pending owner
  review**. Nothing here claims line-by-line manual authorship or review.
- **Reviewer annotations:** hand-crafted `synthetic_example` records. No human review has been
  completed, and the agreement demo (κ = 1/2 on six items) only demonstrates the computation.

## Limits

- Nine controlled fixtures across three tasks. This is not a benchmark, there are no hidden tests, and nothing
  here generalizes to arbitrary correct implementations. The reference and the checks may share blind
  spots.
- SQLite in temp files with fake clocks and fake effects. No performance, throughput or cost measurements.
- Task 3 does not provide exactly-once external effects (see its contract).

## Roadmap (not implemented)

- An optional LLM adapter that produces candidates for evaluation.
- An isolated untrusted-code runner (requirements in `SECURITY.md`).
- Hidden or held-out test variants and a larger fixture corpus.
- Real human maintainability reviews and genuine reviewer agreement.

## Continuous integration

`.github/workflows/ci.yml` re-runs the existing local checks on a GitHub-hosted **Windows** runner.
Windows is the platform the lab was built and tested on, and Linux support has not been verified. The checks are
Ruff lint and format, pytest, the calibrated nine-candidate suite, two fresh suite runs compared
byte for byte with each other and with `reports/`, the documented exit code of each candidate and
the synthetic agreement demo. The workflow uses no secrets, LLM or provider calls, uploads or
deployment. A configured workflow does not show that it passed: see the Actions tab for the actual
run status. The local Stage 3 results are in `BUILD_REPORT.md`.

The build evidence is in [BUILD_REPORT.md](BUILD_REPORT.md). The handoff notes are in
[CHECKPOINT.md](CHECKPOINT.md).
