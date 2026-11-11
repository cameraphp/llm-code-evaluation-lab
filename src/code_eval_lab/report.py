"""Canonical JSON and Markdown reports built from one evidence structure."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from code_eval_lab.registry import PROVENANCE, Candidate, Task
from code_eval_lab.scoring import ERROR, FAIL, MISSING, CheckResult, CheckSpec

REPORT_SCHEMA_VERSION = "2"
TRUST_NOTE = (
    "Allowlisted, digest-pinned fixture imported in-process. This is not a sandbox; only "
    "owner-reviewed fixtures may be evaluated."
)
SUSPECTED_BASIS = (
    "Inferred from the failed assertions only; the test does not prove the root cause. "
    "Confirm by code inspection."
)


def _feedback(manifest: Sequence[CheckSpec], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feedback = []
    for spec, check in zip(manifest, checks, strict=True):
        if check["status"] == FAIL:
            feedback.append(
                {
                    "check_id": spec.id,
                    "severity": spec.severity,
                    "blocking": spec.critical,
                    "taxonomy": spec.taxonomy,
                    "observed_violation": [
                        {k: e[k] for k in ("id", "assertion", "expected", "actual")}
                        for e in check["evidence"]
                        if not e["ok"]
                    ],
                    "suspected_cause": {"statement": spec.suspected_cause, "basis": SUSPECTED_BASIS},
                    "remediation": spec.remediation,
                }
            )
        elif check["status"] in (ERROR, MISSING):
            feedback.append(
                {
                    "check_id": spec.id,
                    "severity": spec.severity,
                    "evaluator_issue": check["error"],
                    "note": "Candidate behaviour for this check was not established; it is "
                    "neither a pass nor a fail.",
                }
            )
    return feedback


def build_report(
    task: Task, candidate: Candidate, results: Sequence[CheckResult], summary: dict[str, Any]
) -> dict[str, Any]:
    first_result: dict[str, CheckResult] = {}
    for result in results:
        first_result.setdefault(result.check_id, result)
    checks = []
    for spec in task.manifest:
        result = first_result.get(spec.id)
        status = summary["check_status"][spec.id]
        error = result.error if result is not None else "no result recorded for declared check"
        checks.append(
            {
                "id": spec.id,
                "title": spec.title,
                "category": spec.category,
                "weight": spec.weight,
                "severity": spec.severity,
                "critical": spec.critical,
                "taxonomy": spec.taxonomy,
                "status": status,
                "points_awarded": summary["check_points"][spec.id],
                "error": error,
                "evidence": [e.as_dict() for e in result.evidence] if result is not None else [],
            }
        )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "lab": "llm-code-evaluation-lab",
        "stage": task.stage,
        "task": {"id": task.id, "title": task.title, "contract_version": task.version},
        "candidate": {
            "id": candidate.id,
            "fixture": candidate.relative_path,
            "fixture_sha256": candidate.sha256,
            "provenance": PROVENANCE,
        },
        "trust_boundary": TRUST_NOTE,
        "evaluation_status": summary["evaluation_status"],
        "verdict": summary["verdict"],
        "automated_score": summary["automated_score"],
        "manual_review": summary["manual_review"],
        "manual_score": summary["manual_score"],
        "review_source": summary["review_source"],
        "total_score": summary["total_score"],
        "blocking_failures": summary["blocking_failures"],
        "failed_checks": summary["failed_checks"],
        "evaluator_problems": summary["evaluator_problems"],
        "checks": checks,
        "feedback": _feedback(task.manifest, checks),
    }


def canonical_json(report: dict[str, Any]) -> str:
    return json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _fmt(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def render_markdown(report: dict[str, Any]) -> str:
    auto = report["automated_score"]
    manual = report["manual_review"]
    total = report["total_score"]
    task, cand = report["task"], report["candidate"]
    auto_text = f"{auto['earned']}/{auto['max']}" if auto else "not published (incomplete)"
    manual_score = report["manual_score"]
    manual_text = manual["status"] + f", source: {report['review_source']}"
    if manual_score is not None:
        manual_text += f", {manual_score['earned']}/{manual_score['max']}"
    total_text = (
        f"{total['earned']}/{total['max']} ({total['basis']})"
        if total
        else "not available until manual review"
    )
    lines = [
        f"# Evaluation: {task['id']} / {cand['id']}",
        "",
        f"- Task: {task['title']} (`{task['contract_version']}`)",
        f"- Fixture: `{cand['fixture']}` (sha256 `{cand['fixture_sha256'][:12]}…`)",
        f"- Provenance: {cand['provenance']}",
        f"- Evaluation status: **{report['evaluation_status']}**",
        f"- Verdict: **{report['verdict']}**",
        f"- Automated score: {auto_text}",
        f"- Manual review ({manual['rubric_id']}, {manual['max']} pts): {manual_text}",
        f"- Total score: {total_text}",
        f"- Blocking failures: {', '.join(report['blocking_failures']) or 'none'}",
        "",
        "| Check | Title | Category | Weight | Severity | Status | Points |",
        "|---|---|---|---:|---|---|---:|",
    ]
    for c in report["checks"]:
        pts = "—" if c["points_awarded"] is None else str(c["points_awarded"])
        lines.append(
            f"| {c['id']} | {c['title']} | {c['category']} | {c['weight']} | {c['severity']} "
            f"| {c['status']} | {pts} |"
        )
    lines += ["", "## Feedback", ""]
    if not report["feedback"]:
        lines.append("No failed or errored checks. Manual maintainability review is still pending.")
    for item in report["feedback"]:
        if "evaluator_issue" in item:
            lines += [
                f"### {item['check_id']} — evaluator issue ({item['severity']})",
                f"- {item['evaluator_issue']}",
                f"- {item['note']}",
                "",
            ]
            continue
        lines.append(
            f"### {item['check_id']} — {item['severity']}{' (blocking)' if item['blocking'] else ''}"
            f", {item['taxonomy']}"
        )
        lines += ["", "Observed violation:", ""]
        for v in item["observed_violation"]:
            lines.append(
                f"- `{v['id']}` {v['assertion']}: expected {_fmt(v['expected'])}, actual {_fmt(v['actual'])}"
            )
        lines += [
            "",
            f"Suspected cause (unproven): {item['suspected_cause']['statement']}",
            "",
            f"Remediation: {item['remediation']}",
            "",
        ]
    lines += ["---", f"_{report['trust_boundary']}_", ""]
    return "\n".join(lines)
