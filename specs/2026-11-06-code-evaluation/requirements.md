# Requirements

Stable IDs. All rows for Stages 1–3 are implemented locally. The roadmap items listed at the end are not.

## Trust boundary (Stage 1)

| ID | Requirement |
|---|---|
| REQ-TB-01 | The CLI selects only allowlisted task and candidate IDs from `registry.py`. It never accepts a path, code, URL, pickle or module name. |
| REQ-TB-02 | Fixture files are SHA-256 pinned (LF-normalised). A digest mismatch refuses execution as a setup error. |
| REQ-TB-03 | Report output is confined to `<project>/artifacts/<subdir>`. Other paths are rejected before any candidate code runs. |
| REQ-TB-04 | No network, `eval`, shell interpolation, package installation or side effects outside per-check temp directories. The docs state that in-process execution is not a sandbox. |

## Task 1 contract (Stage 1)

The full contract is in `examples/task-01-api-idempotency/TASK.md`.

| ID | Requirement | Check |
|---|---|---|
| REQ-T1-01 | A valid new request returns 201 and stores one order and one key record. The stored identity and fields match the response. | T1-C01 |
| REQ-T1-02 | The same key with the same normalized payload returns 200 and the original `order_id` without a new row. A different key creates a distinct order. | T1-C02 |
| REQ-T1-03 | Normalization: item order, currency case, JSON key order and `client_note` are not material. | T1-C03 |
| REQ-T1-04 | A missing or invalid key or an invalid payload returns 422, writes nothing and leaves the key usable. | T1-C04 |
| REQ-T1-05 | The same key with a materially changed payload returns 409 without `order_id`. The original record is unchanged. | T1-S01 |
| REQ-T1-06 | Two independent connections racing on one key behind a barrier store exactly one order. Responses are one 201 and one 200 with the same `order_id`. Joins are bounded. | T1-S02 |
| REQ-T1-07 | After a commit whose response is lost, a retry returns the stored order with exactly one row. | T1-R01 |
| REQ-T1-08 | Replay through a new service and connection after restart returns the same order. | T1-R02 |
| REQ-T1-09 | A failure injected before commit leaves no order and no key. The key stays retryable. | T1-R03 |

## Scoring, gating, reporting (Stage 1)

| ID | Requirement |
|---|---|
| REQ-SC-01 | The manifest is fixed in the evaluator: correctness 40, safety/integrity 30, resilience 20 = 90. Each check has a category, weight, severity and taxonomy, and contributes at most once. |
| REQ-SC-02 | Each check yields PASS, FAIL or ERROR with evidence IDs and expected/actual values. A candidate exception counts as FAIL. An oracle or harness exception counts as ERROR. A check with no assertions counts as ERROR. |
| REQ-SC-03 | Any ERROR, MISSING, duplicate or undeclared result makes the evaluation INCOMPLETE. `automated_score` is then null, and the CLI exits 3. |
| REQ-SC-04 | 10 manual maintainability points (rubric `maintainability-v1`) stay PENDING. `total_score` is null until a human or explicitly synthetic annotation is supplied. |
| REQ-SC-05 | Any failure of a critical check makes the verdict BLOCKED regardless of points. |
| REQ-SC-06 | Verdicts: INCOMPLETE > BLOCKED > CHANGES_REQUESTED (any failure) > REVIEW_PENDING (all pass, no manual review) > ACCEPTABLE (all pass and manual ≥ 6/10). |
| REQ-SC-07 | Candidate metadata or printed claims never affect score or status. |
| REQ-FB-01 | Feedback cites failed evidence and severity, and separates the observed violation from a suspected cause (labelled as unproven). Remediation is bounded. |
| REQ-RP-01 | Canonical JSON (sorted keys, LF) and a Markdown report are built from the same evidence. Identical runs are byte-identical, with no times or machine paths. |
| REQ-CLI-01 | Exit codes: 0 complete and not blocked, 1 complete and BLOCKED, 2 usage or unknown ID or bad output path, 3 setup error or INCOMPLETE. |
| REQ-CAL-01 | Calibration: `reference` passes all checks. `flawed` and `partial` fail their seeded invariants and nothing else. |

### Manual maintainability rubric `maintainability-v1` (10 points, deferred)

Readability and naming (3), separation of validation, persistence and response
construction (3), clarity of error and rollback handling (2), and alignment between code
and the documented contract (2). Stage 1 records `PENDING` and never substitutes 0.

## Task 2 contract (Stage 2)

The full contract is in `examples/task-02-tenant-authorization/TASK.md`.

| ID | Requirement | Check |
|---|---|---|
| REQ-T2-01 | A permitted caller gets their own resource with only the public fields | T2-C01 |
| REQ-T2-02 | Collection reads contain only the caller's tenant rows | T2-C02 |
| REQ-T2-03 | Unauthenticated callers get 401, distinct from authorized access | T2-C03 |
| REQ-T2-04 | An authenticated caller without the required role gets 403 on every operation | T2-C04 |
| REQ-T2-05 | Another tenant's existing ID gets 404, identical to a nonexistent ID, with no data | T2-S01 |
| REQ-T2-06 | A client-supplied tenant, role or user cannot change the trusted scope | T2-S02 |
| REQ-T2-07 | Denials and audit events expose no other-tenant details or tokens | T2-S03 |
| REQ-T2-08 | Malformed requests get 400 without data or exceptions. Input validation is not authorization | T2-R01 |
| REQ-T2-09 | An identity lookup outage fails closed with 503 | T2-R02 |

## Task 3 contract (Stage 2)

The full contract is in `examples/task-03-agent-jobs/TASK.md`.

| ID | Requirement | Check |
|---|---|---|
| REQ-T3-01 | A valid allowlisted job completes once and records its outcome | T3-C01 |
| REQ-T3-02 | An unknown tool or invalid or extra arguments are rejected before any effect | T3-C02 |
| REQ-T3-03 | A permanent error is not retried | T3-C03 |
| REQ-T3-04 | The same key with a changed payload conflicts | T3-C04 |
| REQ-T3-05 | Duplicate delivery does not multiply completed effects | T3-S01 |
| REQ-T3-06 | A dead-lettered job keeps a safe reason and no scheduled attempt | T3-S02 |
| REQ-T3-07 | Attempts and effects stay bounded under repeated delivery (synthetic bound, not a throughput measure) | T3-S03 |
| REQ-T3-08 | Transient failures retry only when due, on the documented schedule | T3-R01 |
| REQ-T3-09 | Exhaustion dead-letters after exactly `max_attempts = 3` (first execution included) | T3-R02 |
| REQ-T3-10 | Restart through a new instance and connection on the same store keeps dedup and attempt counts | T3-R03 |
| REQ-T3-11 | The docs state the effect-atomicity contract and that exactly-once external effects are not guaranteed | TASK.md (documented) |

## Stage 2 cross-cutting

| ID | Requirement |
|---|---|
| REQ-S2-01 | Tasks 2 and 3 reuse the Stage 1 evidence schema, scorer, gating and serializers. Each has its own 40/30/20 manifest |
| REQ-S2-02 | Evidence and feedback never repeat sensitive values (tokens, other-tenant data, exception secrets) |
| REQ-S2-03 | Candidate labels and metadata never affect results. Malformed candidate output counts as FAIL; an unverifiable store counts as ERROR |

## Stage 3: calibration, review and documentation

| ID | Requirement |
|---|---|
| REQ-S3-01 | Reports define `evaluation_status`, `automated_score`, `manual_score`, `review_source`, `total_score` and `verdict` with explicit meanings (RUBRIC.md). A missing manual review leaves the total null |
| REQ-S3-02 | A synthetic annotation yields `SIMULATED_REVIEW`, never an approval. A high manual score cannot override `BLOCKED`. Only a `human` review can reach `ACCEPTABLE` |
| REQ-S3-03 | Duplicate evidence IDs inside a check make it ERROR |
| REQ-S3-04 | The synthetic annotation fixture has six paired items: item ID, reviewer-example ID, category, a score consistent with the category band, a rationale, an evidence reference and provenance `synthetic_example` |
| REQ-S3-05 | Exact agreement and unweighted Cohen's kappa with confusion counts, paired n and source. Missing, unpaired, duplicate and invalid records are defined. Zero pairs or p_e = 1 are undefined (null) |
| REQ-S3-06 | One CLI suite over all registered candidates. Calibration is compared against expectations held outside scoring. A partial run is INCOMPLETE (exit 3). A missed defect is MISCALIBRATED (exit 1) |
| REQ-S3-07 | The compact canonical sample in `reports/` is byte-identical across runs and matches a fresh run |
| REQ-S3-08 | Documentation set with positioning, accurate AI-assisted provenance, a ground-truth limitation, a security model, a build report and a demo outline. Roadmap items are not presented as features |

## Roadmap (not implemented, not authorized)

| ID | Item |
|---|---|
| RM-01 | Optional LLM adapter producing candidates |
| RM-02 | Isolated untrusted-code runner (SECURITY.md) |
| RM-03 | Hidden or held-out test variants and a larger corpus |
| RM-04 | Genuine human maintainability reviews and real reviewer agreement |
| RM-05 | CI and publication (a separate owner decision) |
