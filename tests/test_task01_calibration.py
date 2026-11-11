"""Calibration: real fixtures through the real oracle. Expected outcomes live in tests, not the evaluator."""

from __future__ import annotations

import functools

import pytest

from code_eval_lab import registry
from code_eval_lab.evaluator import evaluate
from code_eval_lab.report import canonical_json


@functools.cache
def report_for(candidate_id: str) -> dict:
    return evaluate("task-01", candidate_id)


def statuses(report: dict) -> dict[str, str]:
    return {c["id"]: c["status"] for c in report["checks"]}


def failed_evidence_ids(report: dict, check_id: str) -> set[str]:
    check = next(c for c in report["checks"] if c["id"] == check_id)
    return {e["id"] for e in check["evidence"] if not e["ok"]}


def test_reference_passes_every_check_but_awaits_manual_review():
    report = report_for("reference")
    assert set(statuses(report).values()) == {"PASS"}
    assert report["evaluation_status"] == "COMPLETE"
    assert report["automated_score"]["earned"] == 90
    assert report["verdict"] == "REVIEW_PENDING"
    assert report["manual_review"]["status"] == "PENDING"
    assert report["manual_score"] is None and report["review_source"] == "none"
    assert report["total_score"] is None
    assert report["feedback"] == []


def test_flawed_fails_exactly_its_seeded_invariants():
    report = report_for("flawed")
    failed = {cid for cid, s in statuses(report).items() if s == "FAIL"}
    assert failed == {"T1-S01", "T1-S02", "T1-R02"}
    assert "ERROR" not in statuses(report).values()
    assert report["verdict"] == "BLOCKED"
    assert report["automated_score"]["earned"] == 90 - 15 - 15 - 8
    # Duplicate write: two orders per race round, two 201s.
    assert "T1-S02:stored_orders" in failed_evidence_ids(report, "T1-S02")
    # Changed payload returns the earlier success for every material variant.
    s01 = failed_evidence_ids(report, "T1-S01")
    for variant in ("customer_ref", "currency", "quantity", "unit_price_minor", "item_added"):
        assert f"T1-S01:variant_{variant}_status" in s01


def test_partial_fails_only_the_remaining_fingerprint_gap():
    report = report_for("partial")
    failed = {cid for cid, s in statuses(report).items() if s == "FAIL"}
    assert failed == {"T1-S01"}
    assert report["verdict"] == "BLOCKED"
    assert report["automated_score"]["earned"] == 75
    s01 = failed_evidence_ids(report, "T1-S01")
    assert "T1-S01:variant_quantity_status" in s01
    assert "T1-S01:variant_unit_price_minor_status" in s01
    assert "T1-S01:variant_customer_ref_status" not in s01  # the partial fix is real


def test_candidate_self_assessment_is_ignored():
    module = registry.load_candidate(registry.get_candidate("task-01", "flawed"))
    assert module.SELF_ASSESSMENT["automated_score"] == 90
    report = report_for("flawed")
    assert report["automated_score"]["earned"] != 90
    assert "SELF_ASSESSMENT" not in canonical_json(report)


def test_feedback_separates_observation_from_suspected_cause():
    item = report_for("partial")["feedback"][0]
    assert item["check_id"] == "T1-S01" and item["severity"] == "critical" and item["blocking"]
    assert all(v["id"].startswith("T1-S01:") for v in item["observed_violation"])
    assert "does not prove the root cause" in item["suspected_cause"]["basis"]
    assert item["remediation"]


@pytest.mark.parametrize("candidate_id", ["reference", "flawed"])
def test_identical_evaluations_are_byte_identical(candidate_id):
    first = canonical_json(evaluate("task-01", candidate_id))
    second = canonical_json(evaluate("task-01", candidate_id))
    assert first == second
    assert str(registry.PROJECT_ROOT) not in first
    assert "Temp" not in first and "tmp" not in first.lower().replace("<tmp>", "")
    assert "ord_" not in first  # raw generated order IDs never enter canonical output
