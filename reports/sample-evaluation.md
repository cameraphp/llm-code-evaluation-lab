# Sample evaluation: all tasks and registered candidates

> This repository is an independent portfolio laboratory. It is not presented as paid RLHF, data-labeling or professional AI-training-company experience. It demonstrates methods for designing, testing and evaluating technical code submissions using controlled fixtures.

Suite status: **CALIBRATED**. 9 candidates evaluated; incomplete: none; calibration mismatches: none.

Every fixture below is a controlled lab implementation (AI-assisted, pending owner review). No real model output was evaluated and no human review was performed.

## Decisions (automated checks actually run)

| Task | Candidate | Status | Automated /90 | Manual /10 | Total /100 | Verdict | Blocking (critical) failures | Calibration |
|---|---|---|---:|---:|---:|---|---|---|
| task-01 | flawed | COMPLETE | 52/90 | — | — | BLOCKED | T1-S01, T1-S02, T1-R02 | match |
| task-01 | partial | COMPLETE | 75/90 | — | — | BLOCKED | T1-S01 | match |
| task-01 | reference | COMPLETE | 90/90 | — | — | REVIEW_PENDING | none | match |
| task-02 | flawed | COMPLETE | 48/90 | — | — | BLOCKED | T2-S01, T2-S02, T2-S03 | match |
| task-02 | partial | COMPLETE | 80/90 | — | — | BLOCKED | T2-C04 | match |
| task-02 | reference | COMPLETE | 90/90 | — | — | REVIEW_PENDING | none | match |
| task-03 | flawed | COMPLETE | 26/90 | — | — | BLOCKED | T3-C02, T3-C04, T3-S01, T3-S03, T3-R02, T3-R03 | match |
| task-03 | partial | COMPLETE | 82/90 | — | — | CHANGES_REQUESTED | none | match |
| task-03 | reference | COMPLETE | 90/90 | — | — | REVIEW_PENDING | none | match |

Exit-style meaning: BLOCKED = a critical contract check failed (independent of the number); CHANGES_REQUESTED = only non-critical failures; REVIEW_PENDING = all automated checks passed, manual review not supplied (no total score). Candidate failures (FAIL) and evaluator errors (ERROR/MISSING) are reported separately; evaluator errors in this run: none.

## Observed failures and suspected causes

Observed = failed evidence IDs from this run. Suspected cause = inferred from those assertions, not proven. Source-based root-cause notes are kept separately in `fixtures/*/DEFECTS.md`.

### task-01 / flawed

- **T1-S01** (critical): `variant_customer_ref_status`, `variant_customer_ref_no_order`, `variant_currency_status`, `variant_currency_no_order`, `variant_quantity_status`, `variant_quantity_no_order`, `variant_unit_price_minor_status`, `variant_unit_price_minor_no_order`, `variant_item_added_status`, `variant_item_added_no_order`
  - Suspected cause (unproven): The request fingerprint is not compared on replay, or it omits material fields.
- **T1-S02** (critical): `statuses`, `same_order_id`, `stored_orders`, `stored_key_records`, `stored_identity`
  - Suspected cause (unproven): Idempotency is not enforced by durable state inside a serialized write transaction (for example a process-local cache or check-then-insert without a unique key).
- **T1-R02** (critical): `replay_status`, `replay_identity`, `stored_orders`, `stored_fields`, `stored_key_records`, `stored_identity`
  - Suspected cause (unproven): Idempotency state is held in memory and lost when the handler or connection restarts.

### task-01 / partial

- **T1-S01** (critical): `variant_quantity_status`, `variant_quantity_no_order`, `variant_unit_price_minor_status`, `variant_unit_price_minor_no_order`
  - Suspected cause (unproven): The request fingerprint is not compared on replay, or it omits material fields.

### task-02 / flawed

- **T2-C01** (major): `fields`, `exposed_categories`
  - Suspected cause (unproven): The read path returns the whole stored row instead of a field allowlist.
- **T2-S01** (critical): `cross_tenant_status`, `cross_tenant_body`, `indistinguishable`, `cross_tenant_exposed`, `reverse_status`, `reverse_no_data`
  - Suspected cause (unproven): The object lookup is keyed by document_id only, without the principal's tenant.
- **T2-S02** (critical): `list_header_ids`, `list_param_ids`, `get_spoofed_status`, `get_spoofed_exposed`
  - Suspected cause (unproven): Request headers or params are consulted when deriving tenant or roles.
- **T2-S03** (critical): `bodies_exact_errors`, `bodies_exposed`, `audit_shape`, `audit_exposed`
  - Suspected cause (unproven): Denial paths serialize the raw request or the stored record into responses or audit events.

### task-02 / partial

- **T2-C04** (critical): `list_status`, `list_body`, `list_no_data`
  - Suspected cause (unproven): The permission check is missing for at least one operation (function-level authorization).

### task-03 / flawed

- **T3-C02** (critical): `case_extra_arg`, `case_bad_pattern_arg`, `case_bad_enum_arg`, `case_sets_max_attempts`, `no_rows`, `no_attempts`, `no_invocations`
  - Suspected cause (unproven): Argument validation checks presence only, not exact keys, types, patterns or enums.
- **T3-C04** (critical): `changed_args_status`, `changed_tool_status`, `other_agent_status`
  - Suspected cause (unproven): Submission overwrites or ignores the stored fingerprint for an existing key.
- **T3-S01** (critical): `statuses_before_run`, `status_after_success`, `duplicate_flag`, `runs`, `applied_effects`
  - Suspected cause (unproven): Redelivery re-queues an existing job (for example insert-or-replace).
- **T3-S02** (major): `no_exception_detail`
  - Suspected cause (unproven): Raw exception text is persisted as the failure reason.
- **T3-S03** (critical): `ok_job_effects`, `failing_job_invocations`, `total_invocations`, `final_states`
  - Suspected cause (unproven): Redelivery resets attempts or state, so the retry bound never takes effect.
- **T3-R02** (critical): `attempts_per_run`, `invocations`, `final_job`
  - Suspected cause (unproven): The attempt bound is off by one or excludes the first execution.
- **T3-R03** (critical): `duplicate_statuses`, `pending_retry_after_restart`, `completed_after_restart`, `attempts_per_run`, `a_applied`, `b_final`
  - Suspected cause (unproven): Dedup or attempt state lives in memory or is reset on resubmission after restart.

### task-03 / partial

- **T3-C03** (major): `later_run`, `invocations`, `final_job`
  - Suspected cause (unproven): Failure handling ignores the error's retryable flag.

## Simulated reviewer component (synthetic_example annotations)

These demonstrate score arithmetic only. A synthetic annotation yields SIMULATED_REVIEW, never an approval, and cannot override a critical automated failure.

| Task | Candidate | Automated | Manual (synthetic) | Total | Verdict |
|---|---|---:|---:|---:|---|
| task-01 | reference | 90/90 | 8/10 | 98/100 | SIMULATED_REVIEW |
| task-02 | flawed | 48/90 | 10/10 | 58/100 | BLOCKED |

## Annotation agreement demo (source: synthetic_example)

Paired items: 6; unpaired: none; missing labels: none. Exact agreement 2/3; expected agreement 1/3; Cohen's kappa 1/2 (defined).

| A \ B | CLEAR | NEEDS_IMPROVEMENT | POOR |
|---|---:|---:|---:|
| CLEAR | 2 | 0 | 0 |
| NEEDS_IMPROVEMENT | 1 | 1 | 0 |
| POOR | 0 | 1 | 1 |

_Hand-crafted synthetic labels on a tiny sample; demonstrates computation only. Not a measure of real human or model agreement, and agreement is not accuracy._
