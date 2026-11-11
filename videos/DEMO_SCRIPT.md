# Demo outline (optional, about 2–3 minutes, English)

This is a guide for a later portfolio demo, not a script to read word for word. The owner verifies
the code and explains it in their own words before recording. It is not a hiring-assessment answer.

## 1. What this is (≈20 s)

- An independent portfolio lab: it designs a code task, runs trusted checks on controlled fixtures,
  scores the result with a gated rubric and writes feedback.
- State plainly that it is not paid RLHF or labeling experience, and that no real model or human
  review is involved.

## 2. One task (≈30 s)

- Open `examples/task-02-tenant-authorization/TASK.md`.
- Point out the processing order: 401, then 403, then 400, then the scoped 404.
- Point out that another tenant's document gets the same 404 as a nonexistent one.

## 3. Flawed candidate, real failing checks (≈45 s)

```powershell
.\.venv\Scripts\python.exe -m code_eval_lab evaluate --task task-02 --candidate flawed
```

- The output shows `BLOCKED` with a score of 48/90, and the exit code is 1.
- Open `artifacts/task-02-flawed/report.md` and show the `T2-S01` evidence. A cross-tenant request
  returns 200, and the report lists `other_tenant_title` and `internal_notes` as categories. The
  values themselves are never printed.

## 4. Score versus gate, and feedback (≈30 s)

- Run the `partial` candidate. It scores 80/90 and is still BLOCKED, because a single critical check
  (`T2-C04`, list without a role check) fails.
- Show a feedback entry. It has the observed violation (with evidence IDs), a suspected cause
  marked unproven, and bounded remediation.
- Mention that the root-cause notes are kept separately in `DEFECTS.md`.

## 5. Calibration and boundaries (≈30 s)

```powershell
.\.venv\Scripts\python.exe -m code_eval_lab evaluate-suite
```

- `CALIBRATED`: 9 candidates, every seeded defect detected, every reference passing.
- Show `reports/sample-evaluation.md`. A synthetic 10/10 manual score cannot unblock a flawed
  candidate, and a synthetic review appears as `SIMULATED_REVIEW`.
- Show the kappa demo: 1/2 on six hand-crafted items, described as a computation demo only.
- Close with the trust boundary: fixtures are allowlisted and digest-pinned, they run in-process,
  and that is not a sandbox (`SECURITY.md`).
