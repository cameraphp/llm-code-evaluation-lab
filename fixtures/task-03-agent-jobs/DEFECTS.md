# Seeded defects: Task 03 fixtures

These notes are for the fixture author. They are **not** candidate-facing, and the evaluator
**does not read them**. The fixtures are controlled lab implementations written with AI assistance and are pending owner review.
They are not outputs from an LLM experiment. Their digests are pinned in `src/code_eval_lab/registry.py`.

## `reference`

Strict schema gate; insert-only dedup with a fingerprint and 409 on conflict; the attempt persisted
before the effect; `max_attempts=3` including the first execution; the backoff schedule [10, 30];
permanent errors dead-lettered immediately; and only the documented reason vocabulary stored.

## `flawed`

| Defect | Code location | Expected observable effect |
|---|---|---|
| F1 Permission gate checks presence only: extra args, extra proposal fields, patterns and enums are not enforced | `invalid_field` | Invalid proposals are accepted and executed |
| F2 Dedup by `INSERT OR REPLACE` | `submit` | Redelivery re-queues jobs; a changed payload overwrites the job; effects multiply; restart does not help |
| F3 Retry bound off by one (`attempt <= MAX_ATTEMPTS`) | `run_due` | 4 attempts before dead-letter |
| F4 Exception text persisted in `last_error_detail` | `_fail` | Fake secret stored in the database |

## `partial`

It fixes F1–F4. One genuine violation remains:

| Defect | Code location | Expected observable effect |
|---|---|---|
| P1 The `retryable` flag is ignored, so every failure is retried | `run_due` except branch | A permanent error is retried up to 3 times. This is a major, not critical, check, so the verdict is CHANGES_REQUESTED |
