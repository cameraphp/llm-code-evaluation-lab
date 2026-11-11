"""Whole-lab calibration suite: every registered candidate, synthetic review demos, agreement demo.

The output is compact and deterministic. Full per-check evidence remains available through
`evaluate` for each candidate.
"""

from __future__ import annotations

import json
from typing import Any

from code_eval_lab import agreement, registry
from code_eval_lab.evaluator import evaluate
from code_eval_lab.scoring import ERROR, FAIL, MISSING

ANNOTATIONS_DIR = registry.PROJECT_ROOT / "annotations"
EXPECTATIONS_PATH = registry.PROJECT_ROOT / "calibration" / "expected-outcomes.json"
SUITE_SCHEMA_VERSION = "1"
DEMO_FIELDS = (
    "task_id", "candidate_id", "verdict", "automated_score",
    "manual_score", "review_source", "total_score", "blocking_failures",
)  # fmt: skip
DECISION_HEADER = (
    "| Task | Candidate | Status | Automated /90 | Manual /10 | Total /100 | Verdict "
    "| Blocking (critical) failures | Calibration |"
)

POSITIONING = (
    "This repository is an independent portfolio laboratory. It is not presented as paid RLHF, "
    "data-labeling or professional AI-training-company experience. It demonstrates methods for "
    "designing, testing and evaluating technical code submissions using controlled fixtures."
)
EVIDENCE_KINDS = {
    "automated_check": "Assertions from trusted oracle checks executed in this run on controlled fixtures.",
    "candidate_failure": "FAIL: the candidate's observed behaviour violated an assertion.",
    "evaluator_error": "ERROR/MISSING: the evaluator could not establish behaviour; never a pass or a zero.",
    "suspected_cause": "Inferred from failed assertions only; not proven by the tests.",
    "source_inspection": "Fixture-author notes with code locations in fixtures/*/DEFECTS.md; separate from "
    "test evidence and never read by the evaluator.",
    "provenance": "Fixtures and docs are AI-assisted and pending owner review. Review annotations are "
    "synthetic_example records. No real model output and no human review are included.",
}


def _compact(report: dict[str, Any]) -> dict[str, Any]:
    auto = report["automated_score"]
    return {
        "task_id": report["task"]["id"],
        "candidate_id": report["candidate"]["id"],
        "fixture_sha256": report["candidate"]["fixture_sha256"],
        "evaluation_status": report["evaluation_status"],
        "verdict": report["verdict"],
        "automated_score": None if auto is None else {"earned": auto["earned"], "max": auto["max"]},
        "manual_score": report["manual_score"],
        "review_source": report["review_source"],
        "total_score": report["total_score"],
        "blocking_failures": report["blocking_failures"],
        "failed_checks": [
            {
                "check_id": c["id"],
                "severity": c["severity"],
                "failed_evidence_ids": [e["id"] for e in c["evidence"] if not e["ok"]],
            }
            for c in report["checks"]
            if c["status"] == FAIL
        ],
        "evaluator_errors": [c["id"] for c in report["checks"] if c["status"] in (ERROR, MISSING)],
        "suspected_causes": {
            f["check_id"]: f["suspected_cause"]["statement"]
            for f in report["feedback"]
            if "suspected_cause" in f
        },
    }


def load_expectations() -> dict[tuple[str, str], dict[str, Any]]:
    data = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))
    return {(e["task_id"], e["candidate_id"]): e for e in data["expected"]}


def _calibrate(entry: dict[str, Any], expected: dict[str, Any] | None) -> dict[str, Any]:
    if expected is None:
        return {"expected_failed_checks": None, "expected_verdict": None, "match": False}
    actual_failed = sorted(f["check_id"] for f in entry["failed_checks"])
    return {
        "expected_failed_checks": sorted(expected["failed_checks"]),
        "expected_verdict": expected["verdict"],
        "match": entry["evaluation_status"] == "COMPLETE"
        and actual_failed == sorted(expected["failed_checks"])
        and entry["verdict"] == expected["verdict"],
    }


def run_suite() -> dict[str, Any]:
    expectations = load_expectations()
    candidates = []
    for task_id, candidate_id in sorted(registry.CANDIDATES):
        entry = _compact(evaluate(task_id, candidate_id))
        entry["calibration"] = _calibrate(entry, expectations.get((task_id, candidate_id)))
        candidates.append(entry)

    manual = json.loads((ANNOTATIONS_DIR / "synthetic-manual-scores.json").read_text(encoding="utf-8"))
    demos = []
    for review in manual["reviews"]:
        entry = _compact(evaluate(review["task_id"], review["candidate_id"], review))
        demos.append({k: entry[k] for k in DEMO_FIELDS})

    labels = agreement.load_annotation_set(ANNOTATIONS_DIR / "synthetic-agreement-example.json")
    reviewer_a, reviewer_b = labels["reviewers"]
    agreement_result = agreement.compute_agreement(labels["records"], reviewer_a, reviewer_b)

    incomplete = [
        f"{c['task_id']}/{c['candidate_id']}" for c in candidates if c["evaluation_status"] != "COMPLETE"
    ]
    mismatched = [f"{c['task_id']}/{c['candidate_id']}" for c in candidates if not c["calibration"]["match"]]
    return {
        "schema_version": SUITE_SCHEMA_VERSION,
        "lab": "llm-code-evaluation-lab",
        "positioning": POSITIONING,
        "evidence_kinds": EVIDENCE_KINDS,
        "summary": {
            "candidates_evaluated": len(candidates),
            "evaluations_incomplete": incomplete,
            "calibration_mismatches": mismatched,
            "suite_status": "INCOMPLETE"
            if incomplete
            else ("CALIBRATED" if not mismatched else "MISCALIBRATED"),
        },
        "candidates": candidates,
        "simulated_review_demos": demos,
        "annotation_agreement_demo": agreement_result,
    }


def _score(value: dict[str, Any] | None) -> str:
    return "—" if value is None else f"{value['earned']}/{value['max']}"


def render_suite_markdown(suite: dict[str, Any]) -> str:
    s = suite["summary"]
    lines = [
        "# Sample evaluation: all tasks and registered candidates",
        "",
        f"> {suite['positioning']}",
        "",
        f"Suite status: **{s['suite_status']}**. {s['candidates_evaluated']} candidates evaluated; "
        f"incomplete: {', '.join(s['evaluations_incomplete']) or 'none'}; "
        f"calibration mismatches: {', '.join(s['calibration_mismatches']) or 'none'}.",
        "",
        "Every fixture below is a controlled lab implementation (AI-assisted, pending owner review). "
        "No real model output was evaluated and no human review was performed.",
        "",
        "## Decisions (automated checks actually run)",
        "",
        DECISION_HEADER,
        "|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for c in suite["candidates"]:
        blocking = ", ".join(c["blocking_failures"]) or "none"
        calibration = "match" if c["calibration"]["match"] else "MISMATCH"
        scores = f"{_score(c['automated_score'])} | {_score(c['manual_score'])} | {_score(c['total_score'])}"
        lines.append(
            f"| {c['task_id']} | {c['candidate_id']} | {c['evaluation_status']} | {scores} "
            f"| {c['verdict']} | {blocking} | {calibration} |"
        )
    lines += [
        "",
        "Exit-style meaning: BLOCKED = a critical contract check failed (independent of the number); "
        "CHANGES_REQUESTED = only non-critical failures; REVIEW_PENDING = all automated checks passed, "
        "manual review not supplied (no total score). Candidate failures (FAIL) and evaluator errors "
        "(ERROR/MISSING) are reported separately; evaluator errors in this run: "
        + (
            ", ".join(
                f"{c['task_id']}/{c['candidate_id']}" for c in suite["candidates"] if c["evaluator_errors"]
            )
            or "none"
        )
        + ".",
        "",
        "## Observed failures and suspected causes",
        "",
        "Observed = failed evidence IDs from this run. Suspected cause = inferred from those assertions, "
        "not proven. Source-based root-cause notes are kept separately in `fixtures/*/DEFECTS.md`.",
        "",
    ]
    for c in suite["candidates"]:
        if not c["failed_checks"]:
            continue
        lines.append(f"### {c['task_id']} / {c['candidate_id']}")
        lines.append("")
        for f in c["failed_checks"]:
            ids = ", ".join(f"`{i.split(':', 1)[1]}`" for i in f["failed_evidence_ids"])
            lines.append(f"- **{f['check_id']}** ({f['severity']}): {ids}")
            lines.append(f"  - Suspected cause (unproven): {c['suspected_causes'][f['check_id']]}")
        lines.append("")
    lines += [
        "## Simulated reviewer component (synthetic_example annotations)",
        "",
        "These demonstrate score arithmetic only. A synthetic annotation yields SIMULATED_REVIEW, never an "
        "approval, and cannot override a critical automated failure.",
        "",
        "| Task | Candidate | Automated | Manual (synthetic) | Total | Verdict |",
        "|---|---|---:|---:|---:|---|",
    ]
    for d in suite["simulated_review_demos"]:
        scores = f"{_score(d['automated_score'])} | {_score(d['manual_score'])} | {_score(d['total_score'])}"
        lines.append(f"| {d['task_id']} | {d['candidate_id']} | {scores} | {d['verdict']} |")
    a = suite["annotation_agreement_demo"]
    exact = a["exact_agreement"]["fraction"] if a["exact_agreement"] else "undefined"
    kappa = a["cohen_kappa"]["fraction"] if a["cohen_kappa"] else "undefined"
    expected = a["expected_agreement"]["fraction"] if a["expected_agreement"] else "undefined"
    lines += [
        "",
        f"## Annotation agreement demo (source: {a['source']})",
        "",
        f"Paired items: {a['paired_n']}; unpaired: {a['unpaired_items'] or 'none'}; missing labels: "
        f"{a['missing_label_items'] or 'none'}. Exact agreement {exact}; expected agreement {expected}; "
        f"Cohen's kappa {kappa} ({a['kappa_status']}).",
        "",
        "| A \\ B | " + " | ".join(a["categories"]) + " |",
        "|---|" + "---:|" * len(a["categories"]),
    ]
    for row in a["categories"]:
        lines.append(
            f"| {row} | " + " | ".join(str(a["confusion"][row][col]) for col in a["categories"]) + " |"
        )
    lines += ["", f"_{a['interpretation_limit']}_", ""]
    return "\n".join(lines)
