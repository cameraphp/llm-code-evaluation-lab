"""Stage 3: agreement arithmetic, suite calibration, sample-report drift and partial runs."""

from __future__ import annotations

import dataclasses
import functools
from types import SimpleNamespace

import pytest

from code_eval_lab import agreement, cli, registry, suite
from code_eval_lab.evaluator import run_check
from code_eval_lab.report import canonical_json
from code_eval_lab.scoring import ERROR

A, B = "example-reviewer-A", "example-reviewer-B"


def rec(item: str, reviewer: str, category: str | None, **extra) -> dict:
    return {
        "item_id": item,
        "reviewer_example_id": reviewer,
        "category": category,
        "rationale": "synthetic rationale",
        "evidence_ref": "fixtures/example.py",
        "provenance": "synthetic_example",
        **extra,
    }


def pairs(a_labels: list, b_labels: list) -> list[dict]:
    return [rec(f"R{i}", A, a) for i, a in enumerate(a_labels)] + [
        rec(f"R{i}", B, b) for i, b in enumerate(b_labels)
    ]


# --- agreement arithmetic --------------------------------------------------------------------


def test_bundled_example_matches_hand_computation():
    labels = agreement.load_annotation_set(suite.ANNOTATIONS_DIR / "synthetic-agreement-example.json")
    result = agreement.compute_agreement(labels["records"], A, B)
    # A: C P N C P N ; B: C P C C N N -> 4/6 match; marginals A(2,2,2) B(3,2,1) -> pe = 12/36
    assert result["paired_n"] == 6 and result["source"] == "synthetic_example"
    assert result["exact_agreement"]["fraction"] == "2/3"
    assert result["expected_agreement"]["fraction"] == "1/3"
    assert result["cohen_kappa"] == {"fraction": "1/2", "value": 0.5}
    assert result["confusion"]["NEEDS_IMPROVEMENT"]["CLEAR"] == 1
    assert result["confusion"]["POOR"]["NEEDS_IMPROVEMENT"] == 1


def test_full_disagreement_gives_negative_kappa():
    result = agreement.compute_agreement(pairs(["CLEAR", "POOR"], ["POOR", "CLEAR"]), A, B)
    # po = 0; marginals A(1/2, 0, 1/2) B(1/2, 0, 1/2) -> pe = 1/2; kappa = (0 - 1/2) / (1/2) = -1
    assert result["exact_agreement"] == {"fraction": "0/1", "value": 0.0}
    assert result["expected_agreement"]["fraction"] == "1/2"
    assert result["cohen_kappa"] == {"fraction": "-1/1", "value": -1.0}


def test_missing_and_unpaired_labels_are_excluded_and_reported():
    records = pairs(["CLEAR", "POOR", None], ["CLEAR", "POOR", "CLEAR"]) + [rec("R9", A, "CLEAR")]
    result = agreement.compute_agreement(records, A, B)
    assert result["paired_n"] == 2
    assert result["missing_label_items"] == ["R2"]
    assert result["unpaired_items"] == ["R9"]


def test_zero_pairs_and_no_variation_are_undefined_not_zero_or_perfect():
    empty = agreement.compute_agreement([rec("R1", A, "CLEAR")], A, B)
    assert empty["paired_n"] == 0
    assert empty["exact_agreement"] is None and empty["cohen_kappa"] is None
    same = agreement.compute_agreement(pairs(["CLEAR", "CLEAR"], ["CLEAR", "CLEAR"]), A, B)
    assert same["exact_agreement"]["value"] == 1.0
    assert same["cohen_kappa"] is None and same["kappa_status"].startswith("undefined")


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ([rec("R1", A, "EXCELLENT")], "invalid category"),
        ([rec("R1", A, "CLEAR"), rec("R1", A, "POOR")], "duplicate"),
        ([rec("R1", A, "CLEAR", score=3)], "outside the CLEAR band"),
        ([rec("R1", A, "CLEAR", provenance="real_human")], "provenance"),
        ([{"item_id": "R1", "category": "CLEAR"}], "missing required keys"),
    ],
)
def test_invalid_annotations_are_rejected(records, message):
    with pytest.raises(agreement.AnnotationError, match=message):
        agreement.compute_agreement(records, A, B)


# --- suite, calibration and canonical sample ---------------------------------------------------


@functools.cache
def suite_result() -> dict:
    return suite.run_suite()


def test_suite_is_calibrated_and_separates_evidence_kinds():
    result = suite_result()
    assert result["summary"]["suite_status"] == "CALIBRATED"
    assert all(c["evaluator_errors"] == [] for c in result["candidates"])
    assert {"automated_check", "candidate_failure", "evaluator_error", "suspected_cause",
            "source_inspection", "provenance"} <= set(result["evidence_kinds"])  # fmt: skip
    demos = {(d["task_id"], d["candidate_id"]): d for d in result["simulated_review_demos"]}
    assert demos[("task-01", "reference")]["verdict"] == "SIMULATED_REVIEW"
    assert demos[("task-02", "flawed")]["verdict"] == "BLOCKED"  # high manual score cannot override
    assert demos[("task-02", "flawed")]["total_score"]["basis"] == "synthetic_example"


def test_committed_sample_report_matches_a_fresh_run():
    reports = registry.PROJECT_ROOT / "reports"
    fresh = canonical_json(suite_result())
    assert (reports / "sample-evaluation.json").read_text(encoding="utf-8") == fresh
    assert (reports / "sample-evaluation.md").read_text(encoding="utf-8") == suite.render_suite_markdown(
        suite_result()
    )
    assert str(registry.PROJECT_ROOT) not in fresh and "\\Temp" not in fresh


def test_partial_run_is_incomplete_and_exits_3(tmp_path, monkeypatch):
    task = registry.get_task("task-03")
    missing = {k: v for k, v in task.checks.items() if k != "T3-R03"}
    monkeypatch.setitem(registry.TASKS, "task-03", dataclasses.replace(task, checks=missing))
    monkeypatch.setattr(cli, "ARTIFACTS_DIR", tmp_path / "artifacts")
    assert cli.main(["evaluate-suite"]) == cli.EXIT_ERROR
    result = suite.run_suite()
    assert result["summary"]["suite_status"] == "INCOMPLETE"
    entry = next(
        c for c in result["candidates"] if c["task_id"] == "task-03" and c["candidate_id"] == "reference"
    )
    assert entry["automated_score"] is None and entry["evaluator_errors"] == ["T3-R03"]


def test_missed_seeded_defect_is_a_calibration_mismatch(tmp_path, monkeypatch):
    real = suite.load_expectations()
    wrong = dict(real)
    wrong[("task-02", "partial")] = {**real[("task-02", "partial")], "failed_checks": []}
    monkeypatch.setattr(suite, "load_expectations", lambda: wrong)
    monkeypatch.setattr(cli, "ARTIFACTS_DIR", tmp_path / "artifacts")
    assert cli.main(["evaluate-suite"]) == cli.EXIT_BLOCKED


def test_duplicate_evidence_ids_make_a_check_error():
    def duplicated(module, workdir, rec):
        rec.expect("same", "first", 1, 1)
        rec.expect("same", "second", 2, 2)

    result = run_check("T1-C01", duplicated, SimpleNamespace())
    assert result.status == ERROR and "duplicate evidence" in result.error
