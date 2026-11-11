"""Stage 2 calibration and safety tests for Task 02 (tenant authorization) and Task 03 (agent jobs).

Expected outcomes live here, never in the evaluator or the fixtures.
"""

from __future__ import annotations

import dataclasses
import functools
from types import SimpleNamespace

import pytest

from code_eval_lab import cli, registry, task02, task03
from code_eval_lab.evaluator import evaluate, run_check
from code_eval_lab.report import canonical_json, render_markdown
from code_eval_lab.scoring import ERROR, FAIL, validate_manifest

CALIBRATION = {
    # (task, candidate): (failed checks, automated score, verdict)
    ("task-02", "reference"): (set(), 90, "REVIEW_PENDING"),
    ("task-02", "flawed"): ({"T2-C01", "T2-S01", "T2-S02", "T2-S03"}, 48, "BLOCKED"),
    ("task-02", "partial"): ({"T2-C04"}, 80, "BLOCKED"),
    ("task-03", "reference"): (set(), 90, "REVIEW_PENDING"),
    ("task-03", "flawed"): (
        {"T3-C02", "T3-C04", "T3-S01", "T3-S02", "T3-S03", "T3-R02", "T3-R03"},
        26,
        "BLOCKED",
    ),
    ("task-03", "partial"): ({"T3-C03"}, 82, "CHANGES_REQUESTED"),
}
SENSITIVE_VALUES = (
    "SECRET-", "tok-north", "tok-south", "@north.example", "@south.example",
    "South pricing", "South vendor", task03.FAKE_SECRET, "upstream timeout", "recipient rejected",
)  # fmt: skip


@functools.cache
def report_for(task_id: str, candidate_id: str) -> dict:
    return evaluate(task_id, candidate_id)


@pytest.mark.parametrize(("task_id", "candidate_id"), sorted(CALIBRATION))
def test_calibration_matches_seeded_design(task_id, candidate_id):
    failed, score, verdict = CALIBRATION[(task_id, candidate_id)]
    report = report_for(task_id, candidate_id)
    assert report["evaluation_status"] == "COMPLETE"
    assert set(report["failed_checks"]) == failed
    assert report["automated_score"]["earned"] == score
    assert report["verdict"] == verdict
    assert report["manual_review"]["status"] == "PENDING" and report["total_score"] is None


def test_partial_repairs_are_real():
    t2 = report_for("task-02", "partial")
    t2_failed = {e["id"] for c in t2["checks"] for e in c["evidence"] if not e["ok"]}
    assert t2_failed == {"T2-C04:list_status", "T2-C04:list_body", "T2-C04:list_no_data"}  # get is gated
    t3 = report_for("task-03", "partial")
    assert {c["id"] for c in t3["checks"] if c["status"] == FAIL} == {"T3-C03"}
    assert t3["blocking_failures"] == []  # non-critical: CHANGES_REQUESTED, not BLOCKED


def test_flawed_bola_is_detected_through_returned_data_not_labels():
    s01 = next(c for c in report_for("task-02", "flawed")["checks"] if c["id"] == "T2-S01")
    exposed = next(e for e in s01["evidence"] if e["id"] == "T2-S01:cross_tenant_exposed")
    assert set(exposed["actual"]) >= {"other_tenant_title", "internal_notes"}


@pytest.mark.parametrize(("task_id", "candidate_id"), sorted(CALIBRATION))
def test_reports_never_repeat_sensitive_values(task_id, candidate_id):
    report = report_for(task_id, candidate_id)
    text = canonical_json(report) + render_markdown(report)
    assert not [v for v in SENSITIVE_VALUES if v in text]


@pytest.mark.parametrize(("task_id", "candidate_id"), sorted(CALIBRATION))
def test_feedback_cites_genuine_failed_evidence(task_id, candidate_id):
    report = report_for(task_id, candidate_id)
    failed_ids = {e["id"] for c in report["checks"] for e in c["evidence"] if not e["ok"]}
    for item in report["feedback"]:
        cited = {v["id"] for v in item["observed_violation"]}
        assert cited and cited <= failed_ids
        assert all(i.startswith(item["check_id"] + ":") for i in cited)
        assert "does not prove the root cause" in item["suspected_cause"]["basis"]


def test_candidate_label_metadata_is_ignored():
    module = registry.load_candidate(registry.get_candidate("task-02", "flawed"))
    assert module.CANDIDATE_LABEL == "reference"
    report = report_for("task-02", "flawed")
    assert report["candidate"]["id"] == "flawed" and report["verdict"] == "BLOCKED"


@pytest.mark.parametrize("task_id", ["task-02", "task-03"])
def test_repeat_evaluation_is_byte_identical(task_id):
    assert canonical_json(evaluate(task_id, "flawed")) == canonical_json(evaluate(task_id, "flawed"))


def test_manifests_are_valid_and_fully_implemented():
    for task in registry.TASKS.values():
        validate_manifest(task.manifest)
        assert set(task.checks) == {s.id for s in task.manifest}


def test_principal_is_immutable():
    principal = task02.PRINCIPALS["tok-north-reader"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        principal.tenant_id = "tenant-south"  # type: ignore[misc]


# --- malformed candidate output vs evaluator errors ----------------------------------------


class MalformedDocumentService:
    def __init__(self, db_path, identity, audit):
        pass

    def handle(self, request):
        return "200 OK"

    def close(self):
        pass


def test_task02_malformed_response_is_fail_not_error():
    result = run_check(
        "T2-C01", task02.check_own_read, SimpleNamespace(DocumentService=MalformedDocumentService)
    )
    assert result.status == FAIL
    status = next(e for e in result.evidence if e.id == "T2-C01:status")
    assert status.actual == "malformed response"


def test_task03_malformed_submit_is_fail_and_missing_store_is_error():
    reference = registry.load_candidate(registry.get_candidate("task-03", "reference"))

    class MalformedSubmit(reference.JobWorker):
        def submit(self, proposal):
            return None

    result = run_check(
        "T3-C02", task03.check_rejects_before_effect, SimpleNamespace(JobWorker=MalformedSubmit)
    )
    assert result.status == FAIL

    class NoStore:
        def __init__(self, db_path, effects, clock):
            pass

        def submit(self, proposal):
            return {"status": 202, "body": {}}

        def run_due(self):
            return 0

        def close(self):
            pass

    result = run_check("T3-C01", task03.check_completes_once, SimpleNamespace(JobWorker=NoStore))
    assert result.status == ERROR  # stored state could not be verified: never a pass or a zero


def test_cli_exit_codes_for_stage2(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ARTIFACTS_DIR", tmp_path / "artifacts")
    assert cli.main(["evaluate", "--task", "task-02", "--candidate", "partial"]) == cli.EXIT_BLOCKED
    assert cli.main(["evaluate", "--task", "task-03", "--candidate", "partial"]) == cli.EXIT_OK
    assert cli.main(["evaluate", "--task", "task-03", "--candidate", "nope"]) == cli.EXIT_USAGE
