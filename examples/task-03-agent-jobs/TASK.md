# Task 03: Agent-proposed background jobs

Version `task-03/v1`. The "agent" is a **synthetic request source** (fixed proposals written by
the harness), not an LLM. Tools are **fake effects** recorded in memory. There is no shell, queue
service or network.

## Interface

```python
class JobWorker:
    def __init__(self, db_path: str, effects: Effects, clock: Clock) -> None: ...  # own sqlite3 connection
    def submit(self, proposal: dict) -> dict: ...   # {"status": int, "body": dict}
    def run_due(self) -> int: ...                   # attempts made in this call
    def close(self) -> None: ...
```

- `clock.now() -> int` is fake time in seconds, controlled by the harness.
- `effects.invoke(tool, args, idempotency_key)` performs a fake tool effect. Errors are exceptions
  with a boolean `retryable` attribute. Their messages may contain sensitive text and must never be
  stored.

## Trusted tool registry (the allowlist)

| Tool | Arguments: exactly these keys, all strings |
|---|---|
| `send_notice` | `recipient_id` matching `^usr-\d{3}$`; `template` in {`welcome`, `reminder`} |
| `archive_document` | `document_id` matching `^doc-\d{3}$` |

A proposal is exactly `{"job_key", "tool", "args", "proposed_by"}`:

- `job_key` matches `^job-[a-z0-9-]{4,40}$` and is the logical idempotency key.
- `proposed_by` matches `^agent-[a-z0-9-]{1,32}$`. It is informational and grants no authority.

Unknown tools, missing, extra or invalid arguments, and extra proposal fields (for example an
attempt to set `max_attempts`) give **422** `{"error": "invalid_proposal", "field": ...}`. Nothing is
stored and no effect runs.

## Deduplication

The fingerprint covers `tool` and `args` (canonical JSON). `proposed_by` is not material.

| Submission | Status | Body |
|---|---|---|
| New key | 202 | `job_key`, `state: "queued"` |
| Known key, same fingerprint, any state | 200 | `job_key`, current `state`, `duplicate: true`. Never re-queued |
| Known key, different fingerprint | 409 | `{"error": "job_key_conflict"}`. The stored job is unchanged |

## Persisted state and retry policy

Minimum observable schema: `jobs(job_key PRIMARY KEY, state, attempts, next_run_at, last_error, ...)`.

- States: `queued` → `succeeded` | `retry_scheduled` | `dead_letter`. A new job has `attempts = 0`
  and `next_run_at = now`.
- `run_due()` attempts each job whose state is `queued` or `retry_scheduled` and whose
  `next_run_at <= now`, once per call. The attempt count is **persisted before** the effect runs.
- **`max_attempts = 3`, including the first execution.** After a retryable failure on attempt
  `n < 3`, the job becomes `retry_scheduled` with `next_run_at = now + [10, 30][n-1]` and
  `last_error = "transient_error"`.
- A retryable failure on attempt 3 makes the job `dead_letter` with `"transient_exhausted"`.
- A non-retryable failure makes the job `dead_letter` immediately with `"permanent_error"`.
- Terminal states (`succeeded`, `dead_letter`) have `next_run_at = NULL` and are never attempted
  again. `last_error` uses only this vocabulary and never contains an exception message.
- All state lives in SQLite, so a new `JobWorker` on the same file keeps deduplication and attempt
  counts.

## Effect atomicity and idempotency, and their limits

The fake effect is **atomic per call** (it raises before applying, or it applies) and **not
idempotent**: every successful call counts as one applied effect. The worker passes `job_key` for
traceability only. The completion ledger in `jobs` bounds re-execution in this lab, but it
**does not prove exactly-once external effects**. If a real remote call timed out after applying,
the worker could not tell, and a retry could apply it twice. The policy here is at-least-once with
a bounded number of attempts. No distributed exactly-once guarantee is claimed.

## Evaluation oracle (evaluator-side summary)

| Check | Assertion |
|---|---|
| T3-C01 | a valid job → 202, `queued` with 0 attempts; one run gives one effect with the exact args; `succeeded`/1; a second run does nothing |
| T3-C02 | 11 invalid proposals → 422 each; 0 rows; 0 effect invocations |
| T3-C03 | permanent error → `dead_letter`, 1 attempt, `permanent_error`; no retry at t=1000 |
| T3-C04 | same key with changed template or tool → 409; a different `proposed_by` → 200; the effect uses the original args |
| T3-S01 | 3 deliveries before the run and 1 after success → [202, 200, 200] and 200; one applied effect |
| T3-S02 | dead-lettered jobs: `last_error` in the vocabulary, no exception detail anywhere in the store, `next_run_at` NULL |
| T3-S03 | 12 rounds of re-delivering an ok job and an always-transient job, with runs every 25 s → ok job 1 effect, transient job 3 invocations, 2 rows |
| T3-R01 | transient, transient, ok with runs at t = 0, 9, 10, 39, 40 → attempts [1,0,1,0,1], next_run_at [10,10,40,40,null] |
| T3-R02 | always transient with runs at t = 0, 10, 40, 1000, 5000 → [1,1,1,0,0], `dead_letter`/3/`transient_exhausted` |
| T3-R03 | three successive worker instances on one file: duplicates still 200, B keeps `attempts=1` across restart, total B invocations 3, A applied once |

Reports never include fake-secret text. A `last_error` value outside the vocabulary is shown
as withheld.
