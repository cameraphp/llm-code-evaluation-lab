# Build report (local, 2026-11-11)

This is the status of the local build after Stages 1–3. Nothing had been published at the end of
Stage 3.

> **Report scope.** This report records the **local** Stage 3 results. These are not hosted CI
> results. The repository was published later in a separate owner-authorized step that added a minimal
> GitHub Actions workflow. That workflow re-runs the checks below. For the hosted evidence, see the Git
> history and the Actions runs. This report is not updated with them.

## Environment

- Windows 11, Python 3.13.7, in a project-local `.venv` (no global changes).
- Runtime dependencies: Python stdlib only. Development dependencies: pytest 9.2.0 and ruff 0.17.4,
  installed from `pyproject.toml` (`.[dev]`).
- Built in one Claude Code session, with AI assistance, across three owner-authorized stages.
  The code, tests and docs are **pending owner review**.

## Checks run (final gate)

| Check | Command | Outcome |
|---|---|---|
| Lint | `.\.venv\Scripts\ruff.exe check src tests fixtures` | All checks passed |
| Format | `.\.venv\Scripts\ruff.exe format --check src tests fixtures` | 29 files already formatted |
| Tests | `.\.venv\Scripts\python.exe -m pytest -q` | 83 passed |
| Suite, run A | `... -m code_eval_lab evaluate-suite --output artifacts\final-run-a` | CALIBRATED, 9/9 complete, exit 0 |
| Suite, run B | `... -m code_eval_lab evaluate-suite --output artifacts\final-run-b` | CALIBRATED, exit 0 |
| Byte stability | SHA-256 of run A, run B and `reports/` | JSON `515E5841…` and MD `F70F8596…`, identical across all three |
| Agreement demo | `... -m code_eval_lab agreement` | n=6, exact agreement 2/3, expected 1/3, κ = 1/2, source `synthetic_example` |
| Per-candidate exits | `... -m code_eval_lab evaluate --task <t> --candidate <c>` | References 0. Blocked candidates 1. task-03 partial 0. No exit 3 |
| Inventory | file listing plus a secret-pattern scan | No stray runtime files and no secret-like strings. The only addresses are fake `*.example` ones |

## Seeded-defect detection

| Task | reference | flawed | partial |
|---|---|---|---|
| task-01 | 90/90 REVIEW_PENDING | 52 BLOCKED (T1-S01, S02, R02) | 75 BLOCKED (T1-S01) |
| task-02 | 90/90 REVIEW_PENDING | 48 BLOCKED (T2-C01, S01, S02, S03) | 80 BLOCKED (T2-C04) |
| task-03 | 90/90 REVIEW_PENDING | 26 BLOCKED (T3-C02, C04, S01, S02, S03, R02, R03) | 82 CHANGES_REQUESTED (T3-C03) |

All nine results match `calibration/expected-outcomes.json`, and therefore the notes in
`fixtures/*/DEFECTS.md`. No evaluator errors occurred for any registered candidate. The ERROR,
MISSING and INCOMPLETE paths are exercised by unit tests that use fake modules or manifests.

## Stage and requirement coverage

| Stage | Requirements | Status |
|---|---|---|
| 1 | REQ-TB, REQ-T1, REQ-SC, REQ-FB, REQ-RP, REQ-CLI, REQ-CAL-01 | Implemented and verified |
| 2 | REQ-T2-01…09, REQ-T3-01…11, REQ-S2-01…03 | Implemented and verified |
| 3 | REQ-S3-01…08 | Implemented and verified |
| Roadmap | RM-01…05 (LLM adapter, isolated runner, hidden tests, real reviews, CI and publication) | Not implemented |

The requirement-to-test map is in `specs/2026-11-06-code-evaluation/validation.md`. The test count
is a by-product of covering the contracts, not a target.

## Synthetic annotation metrics

There are six hand-crafted paired items from `example-reviewer-A` and `example-reviewer-B`. These
are labels, not people. Exact agreement is 2/3, expected agreement 1/3 and Cohen's κ 1/2. The
result **only verifies the computation**. It is not real human or model agreement, it is not
accuracy, and six items support no reliability claim.

The synthetic manual-review demo gives task-01 reference 98/100 `SIMULATED_REVIEW`. For task-02
flawed it gives 58/100, and the verdict stays **BLOCKED** despite a synthetic 10/10.

## Outstanding

- **Owner review** of all nine fixtures, the oracles and the documentation. After any fixture edit,
  pin it again.
- **Genuine human maintainability reviews.** None exist, so `manual_score` is null for every normal
  run.
- **Publication** (Git, licence, GitHub and CI) is a separate owner decision and prompt. Nothing had
  been initialized or pushed at the end of Stage 3. The later publication step chose no licence.
