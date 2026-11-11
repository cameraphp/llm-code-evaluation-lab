"""Command-line entry point.

Exit codes:
  0  evaluation COMPLETE and candidate not blocked (REVIEW_PENDING / CHANGES_REQUESTED)
  1  evaluation COMPLETE and candidate BLOCKED by a critical check
  2  usage error: bad arguments, unknown task/candidate ID, output outside artifacts/
     (no candidate code was executed)
  3  evaluator/setup error (fixture digest/import) or evaluation INCOMPLETE (ERROR/MISSING)

`evaluate-suite` exit codes: 0 every evaluation COMPLETE and matching the calibration
expectations; 1 calibration mismatch (a seeded defect was missed or a reference regressed);
3 setup error or any INCOMPLETE evaluation. Blocked candidates are expected and do not fail it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from code_eval_lab import agreement, registry, suite
from code_eval_lab.evaluator import evaluate
from code_eval_lab.registry import FixtureError, RegistryError
from code_eval_lab.report import canonical_json, render_markdown

EXIT_OK, EXIT_BLOCKED, EXIT_USAGE, EXIT_ERROR = 0, 1, 2, 3
ARTIFACTS_DIR = registry.PROJECT_ROOT / "artifacts"


class OutputPathError(ValueError):
    pass


def resolve_output(arg: str | None, task_id: str, candidate_id: str) -> Path:
    """Resolve --output to a subdirectory of ARTIFACTS_DIR; relative paths use the project root."""
    artifacts = ARTIFACTS_DIR.resolve()
    if arg is None:
        return artifacts / f"{task_id}-{candidate_id}"
    path = Path(arg)
    if not path.is_absolute():
        path = artifacts.parent / path
    path = path.resolve()
    if path == artifacts or not path.is_relative_to(artifacts):
        raise OutputPathError(f"--output must be a subdirectory of {artifacts}")
    return path


def _display(path: Path) -> str:
    try:
        return path.relative_to(ARTIFACTS_DIR.resolve().parent).as_posix()
    except ValueError:
        return str(path)


def _cmd_list() -> int:
    for task in registry.TASKS.values():
        print(f"{task.id}  {task.title} ({task.version})")
        for (task_id, _), cand in sorted(registry.CANDIDATES.items()):
            if task_id == task.id:
                status = registry.digest_status(cand)
                print(f"  {cand.id:<10} {cand.relative_path}  digest={status}")
    return EXIT_OK


def _cmd_evaluate(args: argparse.Namespace) -> int:
    try:
        registry.get_candidate(args.task, args.candidate)
        out_dir = resolve_output(args.output, args.task, args.candidate)
    except (RegistryError, OutputPathError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    try:
        report = evaluate(args.task, args.candidate)
    except FixtureError as exc:
        print(f"setup error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "evaluation.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(canonical_json(report))
    with open(out_dir / "report.md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_markdown(report))

    auto = report["automated_score"]
    score = f"{auto['earned']}/{auto['max']}" if auto else "n/a"
    print(
        f"{args.task}/{args.candidate}: evaluation={report['evaluation_status']} "
        f"verdict={report['verdict']} automated_score={score} "
        f"manual_review={report['manual_review']['status']}"
    )
    if report["blocking_failures"]:
        print(f"blocking failures: {', '.join(report['blocking_failures'])}")
    print(f"wrote {_display(out_dir)}/evaluation.json and report.md")

    if report["evaluation_status"] != "COMPLETE":
        return EXIT_ERROR
    return EXIT_BLOCKED if report["verdict"] == "BLOCKED" else EXIT_OK


def _write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _cmd_suite(args: argparse.Namespace) -> int:
    try:
        out_dir = resolve_output(args.output, "suite", "run")
    except OutputPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.output is None:
        out_dir = ARTIFACTS_DIR.resolve() / "suite"
    try:
        result = suite.run_suite()
    except (FixtureError, agreement.AnnotationError) as exc:
        print(f"setup error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    out_dir.mkdir(parents=True, exist_ok=True)
    _write(out_dir / "sample-evaluation.json", canonical_json(result))
    _write(out_dir / "sample-evaluation.md", suite.render_suite_markdown(result))
    summary = result["summary"]
    print(
        f"suite: {summary['suite_status']} candidates={summary['candidates_evaluated']} "
        f"incomplete={len(summary['evaluations_incomplete'])} "
        f"calibration_mismatches={len(summary['calibration_mismatches'])}"
    )
    print(f"wrote {_display(out_dir)}/sample-evaluation.json and sample-evaluation.md")
    if summary["evaluations_incomplete"]:
        return EXIT_ERROR
    return EXIT_BLOCKED if summary["calibration_mismatches"] else EXIT_OK


def _cmd_agreement() -> int:
    try:
        labels = agreement.load_annotation_set(suite.ANNOTATIONS_DIR / "synthetic-agreement-example.json")
        result = agreement.compute_agreement(labels["records"], *labels["reviewers"])
    except agreement.AnnotationError as exc:
        print(f"invalid annotations: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(json.dumps(result, sort_keys=True, indent=2))
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="code_eval_lab",
        description="Evaluate allowlisted, owner-reviewed fixtures against task contracts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list allowlisted tasks/candidates and fixture digest status")
    ev = sub.add_parser("evaluate", help="evaluate one allowlisted candidate")
    ev.add_argument("--task", required=True, help="task ID: task-01 | task-02 | task-03")
    ev.add_argument("--candidate", required=True, help="candidate ID: reference | flawed | partial")
    ev.add_argument(
        "--output",
        help="directory under artifacts/ (relative to the project root); "
        "default artifacts/<task>-<candidate>",
    )
    st = sub.add_parser("evaluate-suite", help="evaluate every registered candidate plus synthetic demos")
    st.add_argument("--output", help="directory under artifacts/ (default artifacts/suite)")
    sub.add_parser("agreement", help="compute agreement for the bundled synthetic annotation example")
    args = parser.parse_args(argv)
    if args.command == "list":
        return _cmd_list()
    if args.command == "evaluate-suite":
        return _cmd_suite(args)
    if args.command == "agreement":
        return _cmd_agreement()
    return _cmd_evaluate(args)
