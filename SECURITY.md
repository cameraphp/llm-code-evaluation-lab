# Security model

## Trusted-code assumption

This lab executes **only owner-reviewed, controlled fixtures**. Execution is not isolated:
fixtures are imported into the evaluator's own Python process, so a fixture can do anything the
current user can do. Neither a subprocess nor a timeout would change that, because neither is a
sandbox. **Do not register or run untrusted code.**

## Candidate registry

- `src/code_eval_lab/registry.py` maps each `(task_id, candidate_id)` pair to a fixed file under
  `fixtures/`. The CLI accepts IDs only. It never accepts a path, code string, URL, pickle or module
  name.
- Each fixture is pinned by SHA-256, with CRLF normalised to LF. A modified file is refused until
  someone reviews it and updates the pin. `python -m code_eval_lab list` shows `OK`, `MISMATCH` or
  `MISSING` for each fixture.
- A candidate's own metadata, such as a self-assessed score or a self-label, is never read by
  scoring.

## Files, data and services

- Candidates write only to SQLite files in a per-check `TemporaryDirectory`.
- CLI output must be a subdirectory of `artifacts/`, which is git-ignored runtime output. Any other
  path is rejected before candidate code runs. The curated sample in `reports/` is copied by hand
  after review, and a test detects drift between it and a fresh run.
- All data is fictional. Tokens such as `tok-north-reader` and strings such as `SECRET-…` or
  `secret-token-7f3a` are **fake markers**, used to detect leaks. They are never real credentials.
- The lab makes no network calls, LLM or API calls, shell execution, package installation or
  cloud service calls. The Task 3 "tools" are in-memory fakes.

## What a future isolated runner would need

Running untrusted or model-generated code would need a separately designed runner. At minimum it
would need:

- a separate OS-level sandbox, such as a container or microVM with no host mounts;
- CPU, memory, process-count and wall-clock limits enforced by the sandbox, not by Python;
- network access denied by default;
- a read-only filesystem except for one scratch directory, which is destroyed after each run;
- no credentials in the environment, and running as an unprivileged user;
- results returned as data (for example JSON over stdout) and never imported back into the
  evaluator.

This runner is a roadmap item and is **not implemented**.

## Reporting a problem

This is a local portfolio lab with no deployed service. Open a note with the owner rather than
filing a public issue containing any fixture output.
