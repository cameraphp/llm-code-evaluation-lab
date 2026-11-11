# Rubric

Each task is scored out of 100 points: **90 automated** points from trusted checks and **10 manual**
points for maintainability. The manual component is pending in this repository. The weights are
fixed in each task's evaluator-side manifest (`src/code_eval_lab/task0N.py`), and the shared scorer
validates the totals.

## Automated component (90)

| Category | Points | What it covers |
|---|---:|---|
| correctness | 40 | The contract's main behaviour and input handling |
| safety_integrity | 30 | Data integrity, tenant isolation, deduplication and leak-free failure paths |
| resilience | 20 | Restart, failure injection, retry bounds and fail-closed behaviour |

Each check contributes its weight at most once. PASS earns the weight and FAIL earns 0.
ERROR or MISSING earns **nothing and publishes no aggregate**: the evaluation becomes INCOMPLETE.

### Check weights

| Check | Title | Category | Weight | Severity |
|---|---|---|---:|---|
| T1-C01 | New request creates exactly one order with a stable identity | correctness | 10 | major |
| T1-C02 | Same key and payload replays the original; a new key creates a new order | correctness | 10 | major |
| T1-C03 | Normalized-equivalent payload is treated as the same request | correctness | 8 | major |
| T1-C04 | Invalid key or payload is rejected with 422 and writes nothing | correctness | 12 | critical |
| T1-S01 | Same key with a materially changed payload returns 409 conflict | safety_integrity | 15 | critical |
| T1-S02 | Concurrent same-key requests store one order with consistent responses | safety_integrity | 15 | critical |
| T1-R01 | Retry after a committed-but-lost response returns the stored order | resilience | 5 | major |
| T1-R02 | Replay survives a handler and connection restart | resilience | 8 | critical |
| T1-R03 | Failure before commit leaves no order and the key stays retryable | resilience | 7 | critical |
| T2-C01 | Permitted caller reads own document with only public fields | correctness | 12 | major |
| T2-C02 | Collection reads contain only the caller's tenant rows | correctness | 10 | critical |
| T2-C03 | Unauthenticated callers are denied with 401 | correctness | 8 | critical |
| T2-C04 | Authenticated callers without documents:read are denied with 403 | correctness | 10 | critical |
| T2-S01 | Another tenant's document ID cannot be read (BOLA/IDOR) | safety_integrity | 12 | critical |
| T2-S02 | Client-supplied tenant, role or user hints cannot change scope | safety_integrity | 10 | critical |
| T2-S03 | Denials and audit events expose no other-tenant details or tokens | safety_integrity | 8 | critical |
| T2-R01 | Malformed requests are rejected with 400 without data or exceptions | resilience | 10 | major |
| T2-R02 | Identity lookup outage fails closed with 503 | resilience | 10 | critical |
| T3-C01 | Valid allowlisted job completes once and records its outcome | correctness | 12 | major |
| T3-C02 | Unknown tools and invalid or extra arguments are rejected before any effect | correctness | 12 | critical |
| T3-C03 | Permanent errors are not retried | correctness | 8 | major |
| T3-C04 | Same key with a changed payload conflicts | correctness | 8 | critical |
| T3-S01 | Duplicate delivery does not multiply completed effects | safety_integrity | 12 | critical |
| T3-S02 | Dead-lettered jobs keep a safe reason and no scheduled attempt | safety_integrity | 8 | major |
| T3-S03 | Attempts and effects stay bounded under repeated delivery | safety_integrity | 10 | critical |
| T3-R01 | Transient failures retry only when due, on the documented schedule | resilience | 6 | major |
| T3-R02 | Exhausted retries dead-letter after exactly max_attempts | resilience | 6 | critical |
| T3-R03 | Restart preserves completed-job dedup and pending attempt counts | resilience | 8 | critical |

## Report fields

| Field | Meaning |
|---|---|
| `evaluation_status` | `COMPLETE` means every declared check ran to PASS or FAIL. `INCOMPLETE` means at least one check is ERROR or MISSING, or an evaluator problem occurred. |
| `automated_score` | Earned out of 90, by category. It is `null` when the evaluation is incomplete. |
| `manual_score` | Earned out of 10. It is `null` until an annotation is supplied. Pending never counts as 0. |
| `review_source` | `none` (no review), `synthetic_example` (a hand-crafted demonstration) or `human` (a genuine review; none exists in this repo). |
| `total_score` | Automated plus manual out of 100, with its `basis`. It is `null` without a manual score. |
| `verdict` | The contract decision, gated as below. It is independent of the raw number. |

## Verdict gates (highest precedence first)

| Verdict | Condition |
|---|---|
| `INCOMPLETE` | Any ERROR, MISSING, duplicate or undeclared result |
| `BLOCKED` | Any **critical** check failed. A high automated or manual score cannot override it |
| `CHANGES_REQUESTED` | Only non-critical failures, or a human review below 6/10 |
| `REVIEW_PENDING` | All automated checks passed and no manual review was supplied |
| `SIMULATED_REVIEW` | All automated checks passed and a `synthetic_example` annotation was supplied. This only demonstrates arithmetic; it is not an approval |
| `ACCEPTABLE` | All automated checks passed and a **human** review scored at least 6/10. This is never reached in this repository |

## Manual maintainability rubric `maintainability-v1` (10 points)

| Category | Points | Behavioural anchors |
|---|---:|---|
| `CLEAR` | 8–10 | Validation, persistence and response or effect logic sit in separate, named units. Error and rollback paths are explicit. The code reads like the contract, and nothing misleads (no unused tables, no comments contradicting behaviour). |
| `NEEDS_IMPROVEMENT` | 4–7 | The structure is understandable, but there is duplication, implicit coupling or a misleading comment or name. One contract concern is hard to find in the code. |
| `POOR` | 0–3 | The source of truth is unclear (for example process-local state shadowing the store). Mixed responsibilities make defects hard to see. Behaviour contradicts the stated design. |

The four criteria that make up the 10 points are readability and naming (3), separation of concerns
(3), error and rollback clarity (2) and alignment with the contract (2). A record's numeric score must
fall inside its category's band; the agreement tool rejects inconsistent records.

### How a later real reviewer would use it

1. Review a fixture against the anchors and write one record. A record has `item_id`, a reviewer ID,
   `category`, an optional `score`, a short `rationale`, an `evidence_ref` (file and function) and
   `provenance: "human"`.
2. Supply the score as a manual review (`review_source: "human"`) to obtain `total_score` and an
   `ACCEPTABLE` or `CHANGES_REQUESTED` decision. `BLOCKED` still wins over any manual score.
3. For agreement, have two genuine reviewers label the same items independently, then run the
   agreement computation (see `EVALUATION_METHODOLOGY.md`). Six items cannot establish reliability.
