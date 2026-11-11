"""Evidence model, scoring-manifest validation and verdict gating.

Scores are computed only from results of trusted checks declared in the evaluator's manifest.
Nothing a candidate says about itself is consulted.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

AUTOMATED_MAX = 90
CATEGORY_MAX = {"correctness": 40, "safety_integrity": 30, "resilience": 20}
MANUAL_MAX = 10
MANUAL_RUBRIC_ID = "maintainability-v1"
MANUAL_ACCEPT_MIN = 6
SEVERITIES = ("critical", "major", "minor")
TAXONOMY = (
    "logic_correctness",
    "data_integrity_idempotency",
    "authorization_security",  # reserved for Task 2 (planned)
    "retry_resource_behavior",  # reserved for Task 3 (planned)
    "maintainability_manual",
)
REVIEW_SOURCES = ("human", "synthetic_example")  # "none" is reported when no review exists

PASS, FAIL, ERROR, MISSING = "PASS", "FAIL", "ERROR", "MISSING"


class ManifestError(ValueError):
    """The scoring manifest itself is invalid; nothing can be scored."""


@dataclass(frozen=True)
class CheckSpec:
    id: str
    title: str
    category: str
    weight: int
    severity: str
    taxonomy: str
    suspected_cause: str
    remediation: str

    @property
    def critical(self) -> bool:
        return self.severity == "critical"


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return f"<unserializable {type(value).__name__}>"
    return value


def _same(expected: Any, actual: Any) -> bool:
    """Type-strict equality via canonical JSON, so True != 1 and 1.0 != 1."""
    return json.dumps(expected, sort_keys=True) == json.dumps(actual, sort_keys=True)


@dataclass(frozen=True)
class Evidence:
    id: str
    assertion: str
    expected: Any
    actual: Any
    ok: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "assertion": self.assertion,
            "expected": self.expected,
            "actual": self.actual,
            "ok": self.ok,
        }


class CandidateViolation(Exception):
    """The candidate broke the interface contract (e.g. raised from its constructor).

    Recorded as a FAIL with evidence, never as an evaluator ERROR.
    """

    def __init__(self, name: str, assertion: str, actual: str) -> None:
        super().__init__(f"{name}: {actual}")
        self.name = name
        self.assertion = assertion
        self.actual = actual


@dataclass
class Recorder:
    """Collects evidence for one check; every assertion gets a stable evidence ID."""

    check_id: str
    items: list[Evidence] = field(default_factory=list)

    def expect(self, name: str, assertion: str, expected: Any, actual: Any) -> bool:
        actual = _jsonable(actual)
        return self.record(name, assertion, expected, actual, _same(expected, actual))

    def record(self, name: str, assertion: str, expected: Any, actual: Any, ok: bool) -> bool:
        self.items.append(Evidence(f"{self.check_id}:{name}", assertion, expected, _jsonable(actual), ok))
        return ok


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    status: str
    evidence: tuple[Evidence, ...]
    error: str | None = None


def validate_manifest(manifest: Sequence[CheckSpec]) -> None:
    ids = [spec.id for spec in manifest]
    if len(set(ids)) != len(ids):
        raise ManifestError("duplicate check IDs in manifest")
    totals = dict.fromkeys(CATEGORY_MAX, 0)
    for spec in manifest:
        if spec.category not in CATEGORY_MAX:
            raise ManifestError(f"{spec.id}: unknown category {spec.category!r}")
        if spec.severity not in SEVERITIES:
            raise ManifestError(f"{spec.id}: unknown severity {spec.severity!r}")
        if spec.taxonomy not in TAXONOMY:
            raise ManifestError(f"{spec.id}: unknown taxonomy {spec.taxonomy!r}")
        if not isinstance(spec.weight, int) or spec.weight <= 0:
            raise ManifestError(f"{spec.id}: weight must be a positive integer")
        totals[spec.category] += spec.weight
    if totals != CATEGORY_MAX:
        raise ManifestError(f"category weights {totals} != {CATEGORY_MAX}")


def validate_manual_review(review: dict[str, Any] | None) -> dict[str, Any] | None:
    """Accept only an explicit human or explicitly synthetic annotation; None stays pending."""
    if review is None:
        return None
    points = review.get("points")
    source = review.get("review_source")
    if not isinstance(points, int) or isinstance(points, bool) or not 0 <= points <= MANUAL_MAX:
        raise ValueError(f"manual review points must be an integer 0..{MANUAL_MAX}")
    if source not in REVIEW_SOURCES:
        raise ValueError(f"review_source must be one of {REVIEW_SOURCES}")
    if review.get("rubric_id") != MANUAL_RUBRIC_ID:
        raise ValueError(f"rubric_id must be {MANUAL_RUBRIC_ID!r}")
    return {"points": points, "review_source": source}


def summarize(
    manifest: Sequence[CheckSpec],
    results: Iterable[CheckResult],
    manual_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate check results into score, completeness and a gated verdict."""
    validate_manifest(manifest)
    review = validate_manual_review(manual_review)

    problems: list[str] = []
    by_id: dict[str, CheckResult] = {}
    for result in results:
        if result.check_id in by_id:
            problems.append(f"duplicate result for {result.check_id}; counted once")
            continue
        by_id[result.check_id] = result
    declared = {spec.id for spec in manifest}
    problems += [f"result for undeclared check {cid}" for cid in sorted(set(by_id) - declared)]

    statuses: dict[str, str] = {}
    points: dict[str, int | None] = {}
    earned = dict.fromkeys(CATEGORY_MAX, 0)
    for spec in manifest:
        result = by_id.get(spec.id)
        status = result.status if result is not None else MISSING
        if status not in (PASS, FAIL, ERROR, MISSING):
            problems.append(f"{spec.id}: unknown status {status!r}")
            status = ERROR
        statuses[spec.id] = status
        points[spec.id] = spec.weight if status == PASS else 0 if status == FAIL else None
        if status == PASS:
            earned[spec.category] += spec.weight

    complete = not problems and all(s in (PASS, FAIL) for s in statuses.values())
    failed = [spec.id for spec in manifest if statuses[spec.id] == FAIL]
    blocking = [spec.id for spec in manifest if spec.critical and statuses[spec.id] == FAIL]

    if not complete:
        verdict = "INCOMPLETE"
    elif blocking:
        verdict = "BLOCKED"
    elif failed:
        verdict = "CHANGES_REQUESTED"
    elif review is None:
        verdict = "REVIEW_PENDING"
    elif review["review_source"] == "synthetic_example":
        verdict = "SIMULATED_REVIEW"  # demonstrates arithmetic only; never an approval
    elif review["points"] >= MANUAL_ACCEPT_MIN:
        verdict = "ACCEPTABLE"
    else:
        verdict = "CHANGES_REQUESTED"

    automated = None
    if complete:
        automated = {
            "earned": sum(earned.values()),
            "max": AUTOMATED_MAX,
            "by_category": {cat: {"earned": earned[cat], "max": CATEGORY_MAX[cat]} for cat in CATEGORY_MAX},
        }

    review_source = "none" if review is None else review["review_source"]
    manual: dict[str, Any] = {
        "rubric_id": MANUAL_RUBRIC_ID,
        "max": MANUAL_MAX,
        "status": "PENDING" if review is None else "SUPPLIED",
        "review_source": review_source,
    }
    if review_source == "synthetic_example":
        manual["note"] = "explicitly synthetic annotation; not a human review"
    manual_score = None if review is None else {"earned": review["points"], "max": MANUAL_MAX}

    total = None
    if automated is not None and review is not None:
        total = {
            "earned": automated["earned"] + review["points"],
            "max": AUTOMATED_MAX + MANUAL_MAX,
            "basis": review_source,
        }

    return {
        "evaluation_status": "COMPLETE" if complete else "INCOMPLETE",
        "verdict": verdict,
        "automated_score": automated,
        "manual_review": manual,
        "manual_score": manual_score,
        "review_source": review_source,
        "total_score": total,
        "blocking_failures": blocking,
        "failed_checks": failed,
        "evaluator_problems": problems,
        "check_status": statuses,
        "check_points": points,
    }
