"""Run trusted checks against an allowlisted fixture and assemble the evaluation report."""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from code_eval_lab import registry
from code_eval_lab.report import build_report
from code_eval_lab.scoring import (
    ERROR,
    FAIL,
    PASS,
    CandidateViolation,
    CheckResult,
    CheckSpec,
    Evidence,
    Recorder,
    summarize,
    validate_manifest,
)

CheckFn = Callable[[ModuleType, Path, Recorder], None]


def _describe(exc: BaseException, workdir: Path) -> str:
    """Exception summary with machine-specific paths removed (keeps reports deterministic)."""
    message = str(exc)
    for path in (str(workdir), str(workdir.resolve()), tempfile.gettempdir()):
        message = message.replace(path, "<tmp>")
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def run_check(check_id: str, check: CheckFn, module: ModuleType) -> CheckResult:
    """Run one check in a fresh temp directory.

    Candidate contract violations become FAIL with evidence. Any other exception means the
    oracle could not establish behaviour and becomes ERROR, which is never a pass or a zero.
    """
    rec = Recorder(check_id)
    with tempfile.TemporaryDirectory(prefix="code-eval-", ignore_cleanup_errors=True) as tmp:
        workdir = Path(tmp)
        try:
            check(module, workdir, rec)
        except CandidateViolation as violation:
            rec.items.append(
                Evidence(
                    f"{check_id}:{violation.name}",
                    violation.assertion,
                    "no exception",
                    violation.actual,
                    False,
                )
            )
        except Exception as exc:
            return CheckResult(check_id, ERROR, tuple(rec.items), _describe(exc, workdir))
    if not rec.items:
        return CheckResult(check_id, ERROR, (), "check recorded no assertions")
    ids = [item.id for item in rec.items]
    if len(set(ids)) != len(ids):
        return CheckResult(check_id, ERROR, tuple(rec.items), "duplicate evidence IDs; evidence is ambiguous")
    status = PASS if all(item.ok for item in rec.items) else FAIL
    return CheckResult(check_id, status, tuple(rec.items))


def run_checks(
    manifest: Sequence[CheckSpec], checks: Mapping[str, CheckFn], module: ModuleType
) -> list[CheckResult]:
    """Run every declared check that has an implementation; the scorer flags the rest MISSING."""
    return [run_check(spec.id, checks[spec.id], module) for spec in manifest if spec.id in checks]


def evaluate(task_id: str, candidate_id: str, manual_review: dict[str, Any] | None = None) -> dict[str, Any]:
    task = registry.get_task(task_id)
    candidate = registry.get_candidate(task_id, candidate_id)
    validate_manifest(task.manifest)
    module = registry.load_candidate(candidate)
    results = run_checks(task.manifest, task.checks, module)
    summary = summarize(task.manifest, results, manual_review)
    return build_report(task, candidate, results, summary)
