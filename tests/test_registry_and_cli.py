"""Allowlist, digest pinning, output confinement, exit codes and report files."""

from __future__ import annotations

import dataclasses
import json

import pytest

from code_eval_lab import cli, registry


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    target = tmp_path / "artifacts"
    monkeypatch.setattr(cli, "ARTIFACTS_DIR", target)
    return target


@pytest.mark.parametrize(
    ("task_id", "candidate_id"),
    [
        ("task-09", "reference"),
        ("task-01", "golden"),
        ("task-02", "../task-01-api-idempotency/reference"),
        ("task-01", "../fixtures/x"),
        ("task-01", "fixtures/task-01-api-idempotency/reference.py"),
        ("task-01", "os"),
    ],
)
def test_unknown_or_path_like_ids_are_rejected(task_id, candidate_id):
    with pytest.raises(registry.RegistryError):
        registry.get_candidate(task_id, candidate_id)


def test_digest_mismatch_refuses_execution(monkeypatch):
    cand = registry.get_candidate("task-01", "reference")
    tampered = dataclasses.replace(cand, sha256="0" * 64)
    monkeypatch.setitem(registry.CANDIDATES, ("task-01", "reference"), tampered)
    with pytest.raises(registry.FixtureError, match="digest mismatch"):
        registry.load_candidate(tampered)
    assert cli.main(["evaluate", "--task", "task-01", "--candidate", "reference"]) == cli.EXIT_ERROR


def test_all_pinned_fixtures_verify():
    assert {registry.digest_status(c) for c in registry.CANDIDATES.values()} == {"OK"}


@pytest.mark.parametrize("output", ["outside", "artifacts", "artifacts/../escape", "../artifacts/x"])
def test_output_outside_artifacts_is_a_usage_error(artifacts, output):
    code = cli.main(["evaluate", "--task", "task-01", "--candidate", "reference", "--output", output])
    assert code == cli.EXIT_USAGE
    assert not artifacts.exists()


def test_unknown_candidate_exit_code(artifacts):
    assert cli.main(["evaluate", "--task", "task-01", "--candidate", "nope"]) == cli.EXIT_USAGE


def test_cli_writes_reports_and_exit_codes(artifacts):
    assert (
        cli.main(
            [
                "evaluate",
                "--task",
                "task-01",
                "--candidate",
                "reference",
                "--output",
                "artifacts/task01-reference",
            ]
        )
        == cli.EXIT_OK
    )
    out = artifacts / "task01-reference"
    report = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    markdown = (out / "report.md").read_text(encoding="utf-8")
    assert report["verdict"] == "REVIEW_PENDING"
    assert "Automated score: 90/90" in markdown and "PENDING" in markdown
    assert b"\r\n" not in (out / "evaluation.json").read_bytes()
    assert cli.main(["evaluate", "--task", "task-01", "--candidate", "partial"]) == cli.EXIT_BLOCKED
    partial_md = (artifacts / "task-01-partial" / "report.md").read_text(encoding="utf-8")
    assert "T1-S01:variant_quantity_status" in partial_md and "BLOCKED" in partial_md


def test_incomplete_evaluation_exits_3_and_publishes_no_aggregate(artifacts, monkeypatch):
    task = registry.get_task("task-01")
    broken_checks = {k: v for k, v in task.checks.items() if k != "T1-R01"}
    monkeypatch.setitem(registry.TASKS, "task-01", dataclasses.replace(task, checks=broken_checks))
    assert cli.main(["evaluate", "--task", "task-01", "--candidate", "reference"]) == cli.EXIT_ERROR
    report = json.loads((artifacts / "task-01-reference" / "evaluation.json").read_text(encoding="utf-8"))
    assert report["evaluation_status"] == "INCOMPLETE"
    assert report["automated_score"] is None
    assert report["feedback"][0]["check_id"] == "T1-R01"
