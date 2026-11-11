"""Score arithmetic, gating, incomplete evaluations and FAIL-vs-ERROR separation."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from code_eval_lab import registry, task01
from code_eval_lab.evaluator import run_check, run_checks
from code_eval_lab.scoring import (
    ERROR,
    FAIL,
    PASS,
    CheckResult,
    Evidence,
    ManifestError,
    summarize,
    validate_manifest,
)

MANIFEST = task01.MANIFEST


def result(check_id: str, status: str) -> CheckResult:
    return CheckResult(check_id, status, (Evidence(f"{check_id}:x", "a", 1, 1, status == PASS),))


def all_results(**overrides: str) -> list[CheckResult]:
    return [result(s.id, overrides.get(s.id.replace("-", "_"), PASS)) for s in MANIFEST]


def test_manifest_weights_are_fixed_and_explicit():
    validate_manifest(MANIFEST)
    by_cat: dict[str, int] = {}
    for spec in MANIFEST:
        by_cat[spec.category] = by_cat.get(spec.category, 0) + spec.weight
    assert by_cat == {"correctness": 40, "safety_integrity": 30, "resilience": 20}
    assert sum(by_cat.values()) == 90
    assert set(task01.CHECKS) == {s.id for s in MANIFEST}


def test_invalid_manifest_is_rejected():
    broken = (dataclasses.replace(MANIFEST[0], weight=11), *MANIFEST[1:])
    with pytest.raises(ManifestError):
        validate_manifest(broken)
    with pytest.raises(ManifestError):
        validate_manifest((*MANIFEST, MANIFEST[0]))


def test_all_pass_scores_90_and_waits_for_manual_review():
    summary = summarize(MANIFEST, all_results())
    assert summary["automated_score"]["earned"] == 90
    assert summary["verdict"] == "REVIEW_PENDING"
    assert summary["total_score"] is None


def test_critical_failure_blocks_despite_high_score():
    summary = summarize(MANIFEST, all_results(T1_R03=FAIL))
    assert summary["automated_score"]["earned"] == 83
    assert summary["verdict"] == "BLOCKED"
    assert summary["blocking_failures"] == ["T1-R03"]


def test_non_critical_failure_requests_changes():
    summary = summarize(MANIFEST, all_results(T1_C03=FAIL))
    assert summary["automated_score"]["earned"] == 82
    assert summary["verdict"] == "CHANGES_REQUESTED"
    assert summary["blocking_failures"] == []


def test_error_makes_evaluation_incomplete_without_aggregate():
    summary = summarize(MANIFEST, all_results(T1_S02=ERROR))
    assert summary["evaluation_status"] == "INCOMPLETE"
    assert summary["verdict"] == "INCOMPLETE"
    assert summary["automated_score"] is None
    assert summary["check_points"]["T1-S02"] is None  # not a zero


def test_missing_check_makes_evaluation_incomplete():
    results = [r for r in all_results() if r.check_id != "T1-C02"]
    summary = summarize(MANIFEST, results)
    assert summary["check_status"]["T1-C02"] == "MISSING"
    assert summary["automated_score"] is None


def test_duplicate_and_undeclared_results_never_add_points():
    results = [*all_results(T1_C01=FAIL), result("T1-C01", PASS), result("T9-X99", PASS)]
    summary = summarize(MANIFEST, results)
    assert summary["check_status"]["T1-C01"] == FAIL  # first result counted once
    assert summary["evaluation_status"] == "INCOMPLETE"
    assert len(summary["evaluator_problems"]) == 2


def test_synthetic_review_is_simulated_and_only_human_review_can_accept():
    synthetic = {"points": 8, "review_source": "synthetic_example", "rubric_id": "maintainability-v1"}
    summary = summarize(MANIFEST, all_results(), synthetic)
    assert summary["verdict"] == "SIMULATED_REVIEW"
    assert summary["manual_score"] == {"earned": 8, "max": 10}
    assert summary["total_score"] == {"earned": 98, "max": 100, "basis": "synthetic_example"}
    assert "not a human review" in summary["manual_review"]["note"]
    human = {**synthetic, "review_source": "human"}
    assert summarize(MANIFEST, all_results(), human)["verdict"] == "ACCEPTABLE"
    assert summarize(MANIFEST, all_results(), {**human, "points": 3})["verdict"] == "CHANGES_REQUESTED"


def test_high_manual_score_cannot_override_blocking():
    for source in ("synthetic_example", "human"):
        review = {"points": 10, "review_source": source, "rubric_id": "maintainability-v1"}
        blocked = summarize(MANIFEST, all_results(T1_S01=FAIL), review)
        assert blocked["verdict"] == "BLOCKED"
        assert blocked["total_score"]["earned"] == 85  # raw number shown, decision still blocked


def test_pending_review_has_no_manual_or_total_score():
    summary = summarize(MANIFEST, all_results())
    assert summary["manual_score"] is None and summary["total_score"] is None
    assert summary["review_source"] == "none"


@pytest.mark.parametrize(
    "review",
    [
        {"points": 11, "review_source": "human", "rubric_id": "maintainability-v1"},
        {"points": 5, "review_source": "model", "rubric_id": "maintainability-v1"},
        {"points": True, "review_source": "human", "rubric_id": "maintainability-v1"},
    ],
)
def test_invalid_manual_review_is_rejected(review):
    with pytest.raises(ValueError):
        summarize(MANIFEST, all_results(), review)


# --- runner: candidate failures vs evaluator errors -----------------------------------------


class RaisingService:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def create_order(self, request, before_commit=None):
        raise RuntimeError("candidate bug")

    def close(self) -> None:
        pass


class BrokenConstructor:
    def __init__(self, db_path: str) -> None:
        raise OSError("cannot open")


def test_unverifiable_store_is_error_not_pass_or_fail():
    module = SimpleNamespace(OrderService=RaisingService)
    check = run_check("T1-C01", task01.check_create, module)
    # The store was never created, so stored state cannot be verified: that part is ERROR.
    assert check.status == ERROR
    assert "store file was not created" in check.error


def test_constructor_violation_is_a_fail_with_evidence():
    module = SimpleNamespace(OrderService=BrokenConstructor)
    check = run_check("T1-R02", task01.check_restart_replay, module)
    assert check.status == FAIL
    assert check.evidence[-1].id == "T1-R02:construct"
    assert check.evidence[-1].actual == "raised OSError"


def test_candidate_raising_on_create_with_valid_store_is_fail():
    ref = registry.load_candidate(registry.get_candidate("task-01", "reference"))

    class RaisesOnCreate(ref.OrderService):
        def create_order(self, request, before_commit=None):
            raise RuntimeError("candidate bug")

    check = run_check("T1-C01", task01.check_create, SimpleNamespace(OrderService=RaisesOnCreate))
    assert check.status == FAIL
    status = next(e for e in check.evidence if e.id == "T1-C01:status")
    assert status.actual == "raised RuntimeError"


def test_harness_exception_is_error_and_vacuous_check_is_error():
    def harness_bug(module, workdir, rec):
        rec.expect("ok", "first assertion", 1, 1)
        raise KeyError("oracle bug")

    def vacuous(module, workdir, rec):
        return None

    assert run_check("T1-C01", harness_bug, SimpleNamespace()).status == ERROR
    empty = run_check("T1-C01", vacuous, SimpleNamespace())
    assert empty.status == ERROR and empty.error == "check recorded no assertions"


def test_unimplemented_checks_are_reported_missing():
    results = run_checks(MANIFEST, {}, SimpleNamespace())
    assert results == []
    summary = summarize(MANIFEST, results)
    assert set(summary["check_status"].values()) == {"MISSING"}
    assert summary["evaluation_status"] == "INCOMPLETE" and summary["automated_score"] is None
