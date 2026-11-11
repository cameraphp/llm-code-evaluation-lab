"""Paired-label agreement for the maintainability rubric: exact agreement and unweighted Cohen's kappa.

This only demonstrates how the metrics are computed. The bundled labels are hand-crafted
`synthetic_example` records, not independent reviewers. Agreement does not establish accuracy.

Definitions:
- A *record* is one label by one reviewer for one item. Records with `category: null` are
  missing labels.
- An item is *paired* when both reviewers gave it a non-null category. Items labelled by only one
  reviewer are *unpaired*. Missing and unpaired items are reported and excluded from the metrics.
- A duplicate (item_id, reviewer_example_id), an unknown category or provenance, or a score
  outside the category's band makes the whole annotation set invalid. Nothing is silently dropped.
- exact_agreement = matches / paired_n. expected = sum over categories of pA(c) * pB(c), with
  marginals taken over the paired items. kappa = (observed - expected) / (1 - expected).
- If paired_n = 0, both metrics are undefined. If expected = 1, kappa is undefined. In both cases
  the value is reported as null, never as 0 or 1.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

CATEGORIES = ("CLEAR", "NEEDS_IMPROVEMENT", "POOR")
SCORE_BANDS = {"CLEAR": (8, 10), "NEEDS_IMPROVEMENT": (4, 7), "POOR": (0, 3)}
PROVENANCES = ("synthetic_example", "human")
REQUIRED_KEYS = ("item_id", "reviewer_example_id", "category", "rationale", "evidence_ref", "provenance")


class AnnotationError(ValueError):
    """The annotation set violates the documented record contract."""


def validate_records(records: Sequence[Any]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records):
        where = f"record {index}"
        if not isinstance(record, dict) or any(k not in record for k in REQUIRED_KEYS):
            raise AnnotationError(f"{where}: missing required keys {REQUIRED_KEYS}")
        for key in ("item_id", "reviewer_example_id", "rationale", "evidence_ref"):
            if not isinstance(record[key], str) or not record[key]:
                raise AnnotationError(f"{where}: {key} must be a non-empty string")
        if record["provenance"] not in PROVENANCES:
            raise AnnotationError(f"{where}: provenance must be one of {PROVENANCES}")
        category = record["category"]
        if category is not None and category not in CATEGORIES:
            raise AnnotationError(f"{where}: invalid category {category!r}")
        if "score" in record:
            score = record["score"]
            if category is None or not isinstance(score, int) or isinstance(score, bool):
                raise AnnotationError(f"{where}: score requires a category and must be an integer")
            low, high = SCORE_BANDS[category]
            if not low <= score <= high:
                raise AnnotationError(f"{where}: score {score} outside the {category} band {low}-{high}")
        key = (record["item_id"], record["reviewer_example_id"])
        if key in seen:
            raise AnnotationError(f"{where}: duplicate label for item {key[0]} by {key[1]}")
        seen.add(key)
    return list(records)


def _ratio(value: Fraction | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"fraction": f"{value.numerator}/{value.denominator}", "value": round(float(value), 4)}


def compute_agreement(records: Sequence[Any], reviewer_a: str, reviewer_b: str) -> dict[str, Any]:
    validate_records(records)
    labels: dict[str, dict[str, str | None]] = {reviewer_a: {}, reviewer_b: {}}
    sources = set()
    for record in records:
        if record["reviewer_example_id"] in labels:
            labels[record["reviewer_example_id"]][record["item_id"]] = record["category"]
            sources.add(record["provenance"])
    a, b = labels[reviewer_a], labels[reviewer_b]
    items = sorted(set(a) | set(b))
    unpaired = [i for i in items if (i in a) != (i in b)]
    missing = [i for i in items if i in a and i in b and (a[i] is None or b[i] is None)]
    paired = [i for i in items if a.get(i) is not None and b.get(i) is not None]
    n = len(paired)

    confusion = {ca: dict.fromkeys(CATEGORIES, 0) for ca in CATEGORIES}
    for item in paired:
        confusion[a[item]][b[item]] += 1  # type: ignore[index]

    observed = expected = kappa = None
    kappa_status = "undefined: no paired items"
    if n:
        observed = Fraction(sum(confusion[c][c] for c in CATEGORIES), n)
        expected = sum(
            (Fraction(sum(confusion[c].values()), n) * Fraction(sum(confusion[r][c] for r in CATEGORIES), n))
            for c in CATEGORIES
        )
        if expected == 1:
            kappa_status = "undefined: expected agreement is 1 (no category variation)"
        else:
            kappa = (observed - expected) / (1 - expected)
            kappa_status = "defined"

    return {
        "source": sorted(sources)[0] if len(sources) == 1 else sorted(sources),
        "reviewers": [reviewer_a, reviewer_b],
        "categories": list(CATEGORIES),
        "paired_n": n,
        "unpaired_items": unpaired,
        "missing_label_items": missing,
        "exact_agreement": _ratio(observed),
        "expected_agreement": _ratio(expected),
        "cohen_kappa": _ratio(kappa),
        "kappa_status": kappa_status,
        "confusion": confusion,
        "interpretation_limit": (
            "Hand-crafted synthetic labels on a tiny sample; demonstrates computation only. "
            "Not a measure of real human or model agreement, and agreement is not accuracy."
        ),
    }


def load_annotation_set(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise AnnotationError("annotation file must be an object with a 'records' list")
    if data.get("provenance") not in PROVENANCES:
        raise AnnotationError("annotation file provenance must be declared")
    return data
