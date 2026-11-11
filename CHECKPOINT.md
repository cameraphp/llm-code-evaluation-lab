# CHECKPOINT: llm-code-evaluation-lab

This handoff is for a fresh session or TRAE. It is not a declaration of review: all code, tests and docs were
written with AI assistance and are **pending owner review**.

> **Scope note.** This checkpoint describes the state at the **end of Stage 3**, before the
> owner-authorized publication. The repository was published later in a separate step that added a
> minimal CI workflow (`.github/workflows/ci.yml`) and chose no licence. For the publication and the hosted CI
> evidence, see the Git history and the GitHub Actions runs. Statements below that say Git or CI do not exist
> describe the end of Stage 3.

## Location

The project root (a local working copy). The private working prompts in `prompts/` are git-ignored and are not
published. At the end of Stage 3 there was no Git repository, licence, CI or publication.

## Status

**Stages 1–3 are complete locally (2026-11-11). Stop here.** Publication (Git, licence, GitHub, CI)
is a separate owner decision and needs its own prompt. Roadmap items RM-01 to RM-05 in `requirements.md` are not
implemented. RM-05 was later covered only in part: a minimal CI workflow and publication, with no licence.

## Map

- **Tasks:** `examples/task-0N-*/TASK.md` (contracts) and `TASK_SPEC.md` (the index and ground-truth limits).
- **Evaluator:** `src/code_eval_lab/` contains `task01`–`task03` (oracles and manifests), `scoring`, `evaluator`,
  `report`, `registry` (allowlist and pins), `suite`, `agreement` and `cli`.
- **Fixtures:** 9 candidates in `fixtures/`, with seeded-defect notes in each `DEFECTS.md`.
- **Calibration and annotations:** `calibration/expected-outcomes.json` and `annotations/` (all `synthetic_example`).
- **Curated sample:** `reports/sample-evaluation.{json,md}`. A test checks it against a fresh run.
- **Docs:** README, RUBRIC, EVALUATION_METHODOLOGY, SECURITY, BUILD_REPORT and videos/DEMO_SCRIPT.
- **Specs:** `specs/2026-11-06-code-evaluation/{plan,requirements,validation}.md`.

## Commands (from the project root)

```powershell
.\.venv\Scripts\ruff.exe check src tests fixtures
.\.venv\Scripts\ruff.exe format --check src tests fixtures
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m code_eval_lab list
.\.venv\Scripts\python.exe -m code_eval_lab evaluate-suite --output artifacts\suite-check
.\.venv\Scripts\python.exe -m code_eval_lab agreement
.\.venv\Scripts\python.exe -m code_eval_lab evaluate --task task-02 --candidate flawed
```

If a deliberate change alters the suite output, regenerate the curated sample:
`evaluate-suite --output artifacts\suite`, then review and copy both files into `reports\`.

## Last gate (2026-11-11)

- Ruff clean; pytest 83 passed.
- Suite CALIBRATED: 9/9 complete, with all seeded defects detected and all references passing.
- Runs A and B were byte-identical to `reports/`.
- Agreement demo: 2/3 exact agreement, κ = 1/2 on six synthetic items.
- No evaluator errors, and the inventory scan was clean.

## Owner actions before publication

1. Review the nine fixtures, three oracles and the docs. Pin a fixture again after any edit.
2. Decide on licence, Git and publication in a separate prompt.
3. Optionally record a demo following `videos/DEMO_SCRIPT.md`, explaining the code in your own words.
