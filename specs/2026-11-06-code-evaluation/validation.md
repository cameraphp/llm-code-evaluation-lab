# Validation: requirement → check map

Evidence for Stages 1–3 was produced on 2026-11-11 with Python 3.13.7 on Windows, in the local `.venv`.
The final suite has 83 tests. The commands and outcomes are in `BUILD_REPORT.md`.

| Requirement | Verified by | Result |
|---|---|---|
| REQ-TB-01 | `test_unknown_or_path_like_ids_are_rejected`, `test_unknown_candidate_exit_code` | pass |
| REQ-TB-02 | `test_digest_mismatch_refuses_execution`, `test_all_pinned_fixtures_verify`, `list` command | pass |
| REQ-TB-03 | `test_output_outside_artifacts_is_a_usage_error` (4 paths; nothing written) | pass |
| REQ-TB-04 | Design review: no network, `eval`, shell or install code paths. Per-check `TemporaryDirectory`. Not-a-sandbox wording in README, registry and every report | documented |
| REQ-T1-01…09 | Oracle checks T1-C01…T1-R03 (`task01.py`), run against all three fixtures | see calibration |
| REQ-SC-01 | `test_manifest_weights_are_fixed_and_explicit`, `test_invalid_manifest_is_rejected` | pass |
| REQ-SC-02 | `test_constructor_violation_is_a_fail_with_evidence`, `test_candidate_raising_on_create_with_valid_store_is_fail`, `test_harness_exception_is_error_and_vacuous_check_is_error`, `test_unverifiable_store_is_error_not_pass_or_fail` | pass |
| REQ-SC-03 | `test_error_makes_evaluation_incomplete_without_aggregate`, `test_missing_check_makes_evaluation_incomplete`, `test_duplicate_and_undeclared_results_never_add_points`, `test_unimplemented_checks_are_reported_missing`, `test_incomplete_evaluation_exits_3_and_publishes_no_aggregate` | pass |
| REQ-SC-04 | `test_reference_passes_every_check_but_awaits_manual_review`, `test_invalid_manual_review_is_rejected` | pass |
| REQ-SC-05 | `test_critical_failure_blocks_despite_high_score` (83/90 → BLOCKED) | pass |
| REQ-SC-06 | `test_synthetic_review_is_simulated_and_only_human_review_can_accept`, `test_non_critical_failure_requests_changes` | pass |
| REQ-SC-07 | `test_candidate_self_assessment_is_ignored` (`flawed` claims 90/PASS and scores 52) | pass |
| REQ-FB-01 | `test_feedback_separates_observation_from_suspected_cause` | pass |
| REQ-RP-01 | `test_identical_evaluations_are_byte_identical` (reference and flawed; no paths, temp dirs or raw order IDs), LF check in CLI test | pass |
| REQ-CLI-01 | `test_cli_writes_reports_and_exit_codes` (0 and 1), usage tests (2), digest and incomplete tests (3) | pass |
| REQ-CAL-01 | `test_reference_passes_every_check_…`, `test_flawed_fails_exactly_its_seeded_invariants`, `test_partial_fails_only_the_remaining_fingerprint_gap` | pass |
| REQ-T2-01…09 | Oracle checks T2-C01…T2-R02 (`task02.py`) on 3 fixtures, `test_calibration_matches_seeded_design`, `test_partial_repairs_are_real`, `test_flawed_bola_is_detected_through_returned_data_not_labels`, `test_principal_is_immutable` | pass |
| REQ-T3-01…10 | Oracle checks T3-C01…T3-R03 (`task03.py`) on 3 fixtures, `test_calibration_matches_seeded_design`, `test_partial_repairs_are_real` | pass |
| REQ-T3-11 | `examples/task-03-agent-jobs/TASK.md`, section "Effect atomicity and idempotency, and their limits" | documented |
| REQ-S2-01 | `test_manifests_are_valid_and_fully_implemented` (all 3 manifests 40/30/20) | pass |
| REQ-S2-02 | `test_reports_never_repeat_sensitive_values` (6 Stage 2 reports, JSON and Markdown), `test_feedback_cites_genuine_failed_evidence` | pass |
| REQ-S2-03 | `test_candidate_label_metadata_is_ignored`, `test_task02_malformed_response_is_fail_not_error`, `test_task03_malformed_submit_is_fail_and_missing_store_is_error` | pass |
| REQ-S3-01 | `test_pending_review_has_no_manual_or_total_score`, report schema v2, RUBRIC.md field table | pass |
| REQ-S3-02 | `test_synthetic_review_is_simulated_and_only_human_review_can_accept`, `test_high_manual_score_cannot_override_blocking`, suite demo (task-02 flawed stays BLOCKED) | pass |
| REQ-S3-03 | `test_duplicate_evidence_ids_make_a_check_error` | pass |
| REQ-S3-04 | `annotations/synthetic-agreement-example.json`, validated by `agreement.validate_records` | pass |
| REQ-S3-05 | `test_bundled_example_matches_hand_computation` (2/3, 1/3, κ = 1/2), `test_full_disagreement_gives_negative_kappa`, `test_missing_and_unpaired_labels_are_excluded_and_reported`, `test_zero_pairs_and_no_variation_are_undefined_not_zero_or_perfect`, `test_invalid_annotations_are_rejected` (5 cases) | pass |
| REQ-S3-06 | `test_suite_is_calibrated_and_separates_evidence_kinds`, `test_partial_run_is_incomplete_and_exits_3`, `test_missed_seeded_defect_is_a_calibration_mismatch` | pass |
| REQ-S3-07 | `test_committed_sample_report_matches_a_fresh_run`; the final gate compared runs A and B with `reports/` (identical SHA-256) | pass |
| REQ-S3-08 | README, TASK_SPEC, RUBRIC, EVALUATION_METHODOLOGY, SECURITY, BUILD_REPORT, videos/DEMO_SCRIPT | documented |

## Calibration (CLI)

| Candidate | Status | Automated | Verdict | Failed (critical) | Exit |
|---|---|---|---|---|---|
| reference | COMPLETE | 90/90 | REVIEW_PENDING | none | 0 |
| flawed | COMPLETE | 52/90 | BLOCKED | T1-S01, T1-S02, T1-R02 | 1 |
| partial | COMPLETE | 75/90 | BLOCKED | T1-S01 (quantity, unit_price_minor variants only) | 1 |
| task-02 reference | COMPLETE | 90/90 | REVIEW_PENDING | none | 0 |
| task-02 flawed | COMPLETE | 48/90 | BLOCKED | T2-C01 (major), T2-S01, T2-S02, T2-S03 | 1 |
| task-02 partial | COMPLETE | 80/90 | BLOCKED | T2-C04 (list without `documents:read`) | 1 |
| task-03 reference | COMPLETE | 90/90 | REVIEW_PENDING | none | 0 |
| task-03 flawed | COMPLETE | 26/90 | BLOCKED | T3-C02, T3-C04, T3-S01, T3-S02 (major), T3-S03, T3-R02, T3-R03 | 1 |
| task-03 partial | COMPLETE | 82/90 | CHANGES_REQUESTED | T3-C03 (major: permanent error retried) | 0 |

The rows without a task prefix are task-01. Exit 1 means the candidate was correctly blocked;
it is not an evaluator failure. **No genuine evaluator errors (exit 3) occurred for any
registered candidate.** The ERROR, MISSING and INCOMPLETE paths are exercised only by unit tests that use
fake modules or manifests. The task-02 and task-03 evaluations were each run twice through the CLI, and
`evaluation.json` was byte-identical on every rerun.

These results match the seeded defects in each `fixtures/*/DEFECTS.md`. The
evaluator never reads that file.

## Stage check commands

```powershell
.\.venv\Scripts\ruff.exe check src tests fixtures
.\.venv\Scripts\ruff.exe format --check src tests fixtures
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m code_eval_lab evaluate --task task-01 --candidate reference --output artifacts\task01-reference
.\.venv\Scripts\python.exe -m code_eval_lab evaluate --task task-01 --candidate flawed --output artifacts\task01-flawed
.\.venv\Scripts\python.exe -m code_eval_lab evaluate --task task-01 --candidate partial --output artifacts\task01-partial
# Stage 2 (same pattern for flawed and partial; each run twice to confirm byte stability):
.\.venv\Scripts\python.exe -m code_eval_lab evaluate --task task-02 --candidate reference --output artifacts\task-02-reference
.\.venv\Scripts\python.exe -m code_eval_lab evaluate --task task-03 --candidate reference --output artifacts\task-03-reference
```

## Stage 2 repair log

- During development, an evaluator-side leak was found and fixed: the T2 error-body evidence copied
  the raw unexpected body (flawed BOLA response) into the report. That evidence now records key
  names and sensitive categories only (`task02.redacted`). `test_reports_never_repeat_sensitive_values`
  guards it.
- In the full suite, one Stage 1 test failed because it used `task-02` as its example of an
  unknown task ID, and Stage 2 had registered that ID. The example was changed to `task-09`, and a
  path-like candidate ID case for task-02 was added. The test was not weakened.

## Stage 3 notes

- One test was updated deliberately, not relaxed. Prompt 03 required synthetic annotations to show
  `SIMULATED_REVIEW` instead of `ACCEPTABLE`, so the old synthetic-acceptance test now asserts the
  stricter rule. Its `ACCEPTABLE` branch now requires `review_source: "human"`.
- Each repair took one pass: a heredoc newline escape in `cli.py`, line lengths in `suite.py` and
  one loose `or` assertion, which was tightened to exact fractions.
