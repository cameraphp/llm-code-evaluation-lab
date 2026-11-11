# Seeded defects: Task 01 fixtures

Fixture-author documentation. It is **not** candidate-facing task input, and the evaluator
**does not read it**. The evaluator scores only what its checks observe. This file records the
seeded defects so calibration results can be compared with intent.

## Provenance

All three fixtures are controlled lab implementations written for this project with AI
assistance. They are pending owner review. They are not outputs from a measured LLM experiment.
Their SHA-256 digests are pinned in `src/code_eval_lab/registry.py`. Pin them again only after
reviewing a change.

## `reference`

Intended to satisfy the `task-01/v1` contract: a durable `PRIMARY KEY` on the idempotency key,
a fingerprint of the full normalized payload, `BEGIN IMMEDIATE` before lookup, and a single
transaction with rollback.

## `flawed`

| Defect | Code location | Expected observable effect |
|---|---|---|
| F1 duplicate write: the lookup uses a per-instance in-memory cache, and the key table has no unique constraint | `OrderService._recent`, `SCHEMA` | Duplicate orders across independent connections (race) and after restart |
| F2 changed payload accepted: a cache hit returns the earlier success without comparing the payload | `create_order` cache branch | Same key with a changed payload → 200 with the earlier order |
| F3 untrusted self-claim: `SELF_ASSESSMENT` claims 90/PASS | module constant | Must have no effect on score or status |

## `partial`

It fixes F1 (durable `PRIMARY KEY`, `BEGIN IMMEDIATE`, one transaction) and partly fixes F2 (the
fingerprint is compared on replay). One genuine invariant violation remains:

| Defect | Code location | Expected observable effect |
|---|---|---|
| P1 the fingerprint omits `quantity` and `unit_price_minor` (customer, currency and SKU set only) | `request_fingerprint` | Same key with a changed quantity or price → 200 with the earlier order instead of 409 |
