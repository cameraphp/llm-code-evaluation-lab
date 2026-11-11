"""Task 03 oracle: agent-proposed background jobs (contract `task-03/v1`).

Evaluator-side only. The "agent" is a fixed synthetic proposal source; tools are fake effects.
See examples/task-03-agent-jobs/TASK.md.
"""

from __future__ import annotations

import contextlib
import copy
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from code_eval_lab.scoring import CandidateViolation, CheckSpec, Recorder

TASK_ID = "task-03"
TITLE = "Agent-proposed background jobs"
VERSION = "task-03/v1"

KEY_A = "job-notice-0001"
KEY_B = "job-archive-0002"
ARGS_A = {"recipient_id": "usr-101", "template": "welcome"}
ARGS_B = {"document_id": "doc-202"}
ERROR_VOCABULARY = frozenset({"transient_error", "transient_exhausted", "permanent_error"})
FAKE_SECRET = "secret-token-7f3a"  # embedded in fake effect errors; must never be stored or reported
WITHHELD = "<non-vocabulary value withheld>"


class FakeClock:
    def __init__(self) -> None:
        self.t = 0

    def now(self) -> int:
        return self.t


class TransientEffectError(Exception):
    retryable = True


class PermanentEffectError(Exception):
    retryable = False


class FakeEffects:
    """Atomic per call and deliberately NOT idempotent: every successful call is one applied effect.

    `script` maps a job key to outcomes ("ok" | "transient" | "permanent"); the last one repeats.
    """

    def __init__(self, script: dict[str, list[str]] | None = None) -> None:
        self.script = {key: list(outcomes) for key, outcomes in (script or {}).items()}
        self.invocations: list[list[Any]] = []
        self.applied: list[list[Any]] = []

    def invoke(self, tool: Any, args: Any, idempotency_key: Any) -> None:
        record = [str(tool), copy.deepcopy(args), str(idempotency_key)]
        self.invocations.append(record)
        plan = self.script.get(record[2])
        outcome = (plan.pop(0) if len(plan) > 1 else plan[0]) if plan else "ok"
        if outcome == "transient":
            raise TransientEffectError(f"upstream timeout ({FAKE_SECRET})")
        if outcome == "permanent":
            raise PermanentEffectError(f"recipient rejected ({FAKE_SECRET})")
        self.applied.append(record)

    def invoked(self, key: str) -> int:
        return sum(1 for r in self.invocations if r[2] == key)

    def applied_for(self, key: str) -> int:
        return sum(1 for r in self.applied if r[2] == key)


def proposal(
    key: str = KEY_A, tool: Any = "send_notice", args: Any = None, by: str = "agent-synth-1"
) -> dict[str, Any]:
    return {"job_key": key, "tool": tool, "args": ARGS_A if args is None else args, "proposed_by": by}


@dataclass(frozen=True)
class Outcome:
    status: int | None
    body: dict[str, Any]
    raised: str | None

    @property
    def observed(self) -> int | str:
        if self.raised is not None:
            return f"raised {self.raised}"
        return self.status if self.status is not None else "malformed response"


def submit(worker: Any, prop: Any) -> Outcome:
    try:
        response = worker.submit(copy.deepcopy(prop))
    except Exception as exc:
        return Outcome(None, {}, type(exc).__name__)
    if not isinstance(response, dict):
        return Outcome(None, {}, None)
    status, body = response.get("status"), response.get("body")
    return Outcome(
        status if isinstance(status, int) and not isinstance(status, bool) else None,
        copy.deepcopy(body) if isinstance(body, dict) else {},
        None,
    )


def run(worker: Any) -> int | str:
    try:
        made = worker.run_due()
    except Exception as exc:
        return f"raised {type(exc).__name__}"
    return made if isinstance(made, int) and not isinstance(made, bool) else "malformed result"


@contextlib.contextmanager
def open_worker(module: ModuleType, db: Path, effects: FakeEffects, clock: FakeClock) -> Iterator[Any]:
    try:
        worker = module.JobWorker(str(db), effects, clock)
    except Exception as exc:
        raise CandidateViolation(
            "construct",
            "JobWorker(db_path, effects, clock) constructs without raising",
            f"raised {type(exc).__name__}",
        ) from exc
    try:
        yield worker
    finally:
        with contextlib.suppress(Exception):
            worker.close()


def safe_error(value: Any) -> Any:
    return value if value is None or value in ERROR_VOCABULARY else WITHHELD


def read_jobs(db: Path) -> dict[str, list[Any]]:
    """job_key -> [state, attempts, next_run_at, last_error (vocabulary or withheld)]."""
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=5.0)
    try:
        rows = conn.execute(
            "SELECT job_key, state, attempts, next_run_at, last_error FROM jobs ORDER BY job_key"
        ).fetchall()
    finally:
        conn.close()
    return {key: [state, attempts, nxt, safe_error(err)] for key, state, attempts, nxt, err in rows}


def store_contains(db: Path, needles: tuple[str, ...]) -> bool:
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=5.0)
    try:
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    return any(n in dump for n in needles)


# --- checks ------------------------------------------------------------------------------


def check_completes_once(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db, effects, clock = workdir / "jobs.db", FakeEffects(), FakeClock()
    with open_worker(module, db, effects, clock) as worker:
        accepted = submit(worker, proposal())
        queued = read_jobs(db).get(KEY_A)
        first = run(worker)
        second = run(worker)
    rec.expect("submit_status", "valid allowlisted proposal returns 202", 202, accepted.observed)
    rec.expect(
        "queued_state", "stored as queued with 0 attempts", ["queued", 0], queued[:2] if queued else None
    )
    rec.expect("first_run", "first run_due makes one attempt", 1, first)
    rec.expect("second_run", "second run_due makes no attempt", 0, second)
    rec.expect(
        "applied",
        "exactly one effect with the exact args and key",
        [["send_notice", ARGS_A, KEY_A]],
        effects.applied,
    )
    rec.expect(
        "final_job",
        "job recorded as succeeded after 1 attempt",
        ["succeeded", 1, None, None],
        read_jobs(db).get(KEY_A),
    )


def _invalid_proposals() -> list[tuple[str, Any]]:
    return [
        ("unknown_tool", proposal(tool="run_shell", args={"command": "echo hi"})),
        ("tool_not_string", proposal(tool=["send_notice"])),
        ("extra_arg", proposal(args={**ARGS_A, "cc": "usr-999"})),
        ("missing_arg", proposal(args={"recipient_id": "usr-101"})),
        ("wrong_type_arg", proposal(args={"recipient_id": 101, "template": "welcome"})),
        ("bad_pattern_arg", proposal(args={"recipient_id": "usr-1", "template": "welcome"})),
        ("bad_enum_arg", proposal(args={"recipient_id": "usr-101", "template": "promo-blast"})),
        ("args_not_object", proposal(args="recipient_id=usr-101")),
        ("bad_job_key", proposal(key="JOB 1")),
        ("missing_job_key", {k: v for k, v in proposal().items() if k != "job_key"}),
        ("sets_max_attempts", {**proposal(), "max_attempts": 50}),
    ]


def check_rejects_before_effect(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db, effects, clock = workdir / "jobs.db", FakeEffects(), FakeClock()
    with open_worker(module, db, effects, clock) as worker:
        outcomes = [(name, submit(worker, prop)) for name, prop in _invalid_proposals()]
        made = run(worker)
    for name, outcome in outcomes:
        rec.expect(f"case_{name}", f"invalid proposal '{name}' returns 422", 422, outcome.observed)
    rec.expect("no_rows", "no job rows stored", 0, len(read_jobs(db)))
    rec.expect("no_attempts", "run_due makes no attempt", 0, made)
    rec.expect("no_invocations", "no effect was invoked", 0, len(effects.invocations))


def check_permanent_not_retried(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db, effects, clock = workdir / "jobs.db", FakeEffects({KEY_A: ["permanent"]}), FakeClock()
    with open_worker(module, db, effects, clock) as worker:
        submit(worker, proposal())
        first = run(worker)
        clock.t = 1000
        later = run(worker)
    rec.expect("first_run", "first run makes one attempt", 1, first)
    rec.expect("later_run", "no retry after a permanent error", 0, later)
    rec.expect("invocations", "effect invoked exactly once", 1, effects.invoked(KEY_A))
    rec.expect(
        "final_job",
        "dead_letter after 1 attempt with permanent_error",
        ["dead_letter", 1, None, "permanent_error"],
        read_jobs(db).get(KEY_A),
    )


def check_changed_payload_conflicts(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db, effects, clock = workdir / "jobs.db", FakeEffects(), FakeClock()
    with open_worker(module, db, effects, clock) as worker:
        first = submit(worker, proposal())
        changed_args = submit(worker, proposal(args={**ARGS_A, "template": "reminder"}))
        changed_tool = submit(worker, proposal(tool="archive_document", args=ARGS_B))
        other_agent = submit(worker, proposal(by="agent-synth-2"))
        run(worker)
    rec.expect("first_status", "first submission returns 202", 202, first.observed)
    rec.expect("changed_args_status", "same key with changed args returns 409", 409, changed_args.observed)
    rec.expect(
        "changed_tool_status", "same key with a different tool returns 409", 409, changed_tool.observed
    )
    rec.expect("other_agent_status", "proposed_by is not material: 200 duplicate", 200, other_agent.observed)
    rec.expect(
        "applied", "the effect used the original args only", [["send_notice", ARGS_A, KEY_A]], effects.applied
    )
    rec.expect("rows", "one job row stored", 1, len(read_jobs(db)))


def check_duplicate_delivery(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db, effects, clock = workdir / "jobs.db", FakeEffects(), FakeClock()
    with open_worker(module, db, effects, clock) as worker:
        before = [submit(worker, proposal()).observed for _ in range(3)]
        runs = [run(worker)]
        after = submit(worker, proposal())
        runs.append(run(worker))
        clock.t = 100
        runs.append(run(worker))
    rec.expect("statuses_before_run", "three deliveries: 202 then duplicates", [202, 200, 200], before)
    rec.expect("status_after_success", "redelivery after success is a 200 duplicate", 200, after.observed)
    rec.expect("duplicate_flag", "redelivery body reports duplicate: true", True, after.body.get("duplicate"))
    rec.expect("runs", "attempts per run", [1, 0, 0], runs)
    rec.expect("applied_effects", "exactly one applied effect", 1, effects.applied_for(KEY_A))
    rec.expect(
        "final_job", "job succeeded after 1 attempt", ["succeeded", 1, None, None], read_jobs(db).get(KEY_A)
    )


def check_dead_letter_safe(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    effects = FakeEffects({KEY_A: ["permanent"], KEY_B: ["transient"]})
    db, clock = workdir / "jobs.db", FakeClock()
    with open_worker(module, db, effects, clock) as worker:
        submit(worker, proposal())
        submit(worker, proposal(key=KEY_B, tool="archive_document", args=ARGS_B))
        for t in (0, 10, 40, 1000):
            clock.t = t
            run(worker)
    jobs = read_jobs(db)
    final = [jobs.get(KEY_A, [None] * 4), jobs.get(KEY_B, [None] * 4)]
    rec.expect(
        "states", "both jobs end in dead_letter", ["dead_letter", "dead_letter"], [j[0] for j in final]
    )
    rec.expect(
        "next_run", "dead-lettered jobs have no scheduled attempt", [None, None], [j[2] for j in final]
    )
    rec.expect(
        "reasons_in_vocabulary",
        "last_error uses only the safe vocabulary",
        True,
        all(j[3] in ERROR_VOCABULARY for j in final),
    )
    rec.expect(
        "no_exception_detail",
        "no exception message or secret is stored anywhere",
        False,
        store_contains(db, (FAKE_SECRET, "upstream timeout", "recipient rejected")),
    )


def check_bounded_redelivery(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    effects = FakeEffects({KEY_B: ["transient"]})
    db, clock = workdir / "jobs.db", FakeClock()
    with open_worker(module, db, effects, clock) as worker:
        for _ in range(12):
            submit(worker, proposal())
            submit(worker, proposal(key=KEY_B, tool="archive_document", args=ARGS_B))
            run(worker)
            clock.t += 25
    jobs = read_jobs(db)
    rec.expect(
        "ok_job_effects", "ok job applied exactly once over 12 deliveries", 1, effects.applied_for(KEY_A)
    )
    rec.expect(
        "failing_job_invocations", "failing job invoked max_attempts (3) times", 3, effects.invoked(KEY_B)
    )
    rec.expect("total_invocations", "total invocations stay bounded at 4", 4, len(effects.invocations))
    rec.expect("rows", "two job rows", 2, len(jobs))
    rec.expect(
        "final_states",
        "final states succeeded / dead_letter",
        ["succeeded", "dead_letter"],
        [jobs.get(KEY_A, [None])[0], jobs.get(KEY_B, [None])[0]],
    )


def check_retry_schedule(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    effects = FakeEffects({KEY_A: ["transient", "transient", "ok"]})
    db, clock = workdir / "jobs.db", FakeClock()
    runs, next_runs = [], []
    with open_worker(module, db, effects, clock) as worker:
        submit(worker, proposal())
        for t in (0, 9, 10, 39, 40):
            clock.t = t
            runs.append(run(worker))
            next_runs.append(read_jobs(db).get(KEY_A, [None] * 4)[2])
    rec.expect("attempts_per_run", "attempts only when due (t=0,9,10,39,40)", [1, 0, 1, 0, 1], runs)
    rec.expect("next_run_at", "backoff schedule 10 s then 30 s", [10, 10, 40, 40, None], next_runs)
    rec.expect("invocations", "three invocations in total", 3, effects.invoked(KEY_A))
    rec.expect("applied", "one applied effect", 1, effects.applied_for(KEY_A))
    rec.expect(
        "final_job", "succeeded after 3 attempts", ["succeeded", 3, None, None], read_jobs(db).get(KEY_A)
    )


def check_exhaustion(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    effects = FakeEffects({KEY_A: ["transient"]})
    db, clock = workdir / "jobs.db", FakeClock()
    runs = []
    with open_worker(module, db, effects, clock) as worker:
        submit(worker, proposal())
        for t in (0, 10, 40, 1000, 5000):
            clock.t = t
            runs.append(run(worker))
    rec.expect("attempts_per_run", "exactly max_attempts=3 attempts, then none", [1, 1, 1, 0, 0], runs)
    rec.expect("invocations", "three invocations in total", 3, effects.invoked(KEY_A))
    rec.expect(
        "final_job",
        "dead_letter after 3 attempts with transient_exhausted",
        ["dead_letter", 3, None, "transient_exhausted"],
        read_jobs(db).get(KEY_A),
    )


def check_restart_persistence(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    effects = FakeEffects({KEY_B: ["transient", "transient", "ok"]})
    db, clock = workdir / "jobs.db", FakeClock()
    prop_b = proposal(key=KEY_B, tool="archive_document", args=ARGS_B)
    runs, duplicates = [], []
    with open_worker(module, db, effects, clock) as worker:
        submit(worker, proposal())
        submit(worker, prop_b)
        runs.append(run(worker))
    with open_worker(module, db, effects, clock) as restarted:  # new instance + connection
        duplicates += [submit(restarted, proposal()).observed, submit(restarted, prop_b).observed]
        mid = read_jobs(db)
        clock.t = 10
        runs.append(run(restarted))
    with open_worker(module, db, effects, clock) as again:
        clock.t = 40
        runs.append(run(again))
        duplicates.append(submit(again, proposal()).observed)
    final = read_jobs(db)
    rec.expect(
        "duplicate_statuses", "redeliveries after restart are 200 duplicates", [200, 200, 200], duplicates
    )
    rec.expect(
        "pending_retry_after_restart",
        "B keeps attempts=1 and its schedule across restart",
        ["retry_scheduled", 1, 10, "transient_error"],
        mid.get(KEY_B),
    )
    rec.expect(
        "completed_after_restart",
        "A stays succeeded across restart",
        ["succeeded", 1, None, None],
        mid.get(KEY_A),
    )
    rec.expect("attempts_per_run", "attempts per run across three instances", [2, 1, 1], runs)
    rec.expect("a_applied", "A applied exactly once", 1, effects.applied_for(KEY_A))
    rec.expect(
        "b_invocations", "B invoked 3 times in total (bound kept across restarts)", 3, effects.invoked(KEY_B)
    )
    rec.expect("b_final", "B succeeded on attempt 3", ["succeeded", 3, None, None], final.get(KEY_B))


# --- manifest ----------------------------------------------------------------------------
# Positional fields: id, title, category, weight, severity, taxonomy, suspected_cause, remediation.
# fmt: off
MANIFEST: tuple[CheckSpec, ...] = (
    CheckSpec(
        "T3-C01", "Valid allowlisted job completes once and records its outcome",
        "correctness", 12, "major", "logic_correctness",
        "Execution or outcome recording does not follow the documented state machine.",
        "Persist queued -> succeeded with attempts and clear next_run_at on success.",
    ),
    CheckSpec(
        "T3-C02", "Unknown tools and invalid or extra arguments are rejected before any effect",
        "correctness", 12, "critical", "authorization_security",
        "Argument validation checks presence only, not exact keys, types, patterns or enums.",
        "Validate proposals against the exact tool schema (no extra keys or fields) before storing.",
    ),
    CheckSpec(
        "T3-C03", "Permanent errors are not retried",
        "correctness", 8, "major", "retry_resource_behavior",
        "Failure handling ignores the error's retryable flag.",
        "Dead-letter immediately with permanent_error when retryable is false.",
    ),
    CheckSpec(
        "T3-C04", "Same key with a changed payload conflicts",
        "correctness", 8, "critical", "data_integrity_idempotency",
        "Submission overwrites or ignores the stored fingerprint for an existing key.",
        "Store a fingerprint of tool and args; return 409 and leave the job unchanged on mismatch.",
    ),
    CheckSpec(
        "T3-S01", "Duplicate delivery does not multiply completed effects",
        "safety_integrity", 12, "critical", "data_integrity_idempotency",
        "Redelivery re-queues an existing job (for example insert-or-replace).",
        "Insert new keys only; answer known keys with a 200 duplicate and never reset state.",
    ),
    CheckSpec(
        "T3-S02", "Dead-lettered jobs keep a safe reason and no scheduled attempt",
        "safety_integrity", 8, "major", "retry_resource_behavior",
        "Raw exception text is persisted as the failure reason.",
        "Persist only the documented reason vocabulary; keep exception details out of the store.",
    ),
    CheckSpec(
        "T3-S03", "Attempts and effects stay bounded under repeated delivery",
        "safety_integrity", 10, "critical", "retry_resource_behavior",
        "Redelivery resets attempts or state, so the retry bound never takes effect.",
        "Make redelivery side-effect free and enforce max_attempts from persisted attempts.",
    ),
    CheckSpec(
        "T3-R01", "Transient failures retry only when due, on the documented schedule",
        "resilience", 6, "major", "retry_resource_behavior",
        "Backoff is computed from the wrong attempt index or due time is ignored.",
        "Schedule next_run_at = now + [10, 30][attempt-1] and only run jobs with next_run_at <= now.",
    ),
    CheckSpec(
        "T3-R02", "Exhausted retries dead-letter after exactly max_attempts",
        "resilience", 6, "critical", "retry_resource_behavior",
        "The attempt bound is off by one or excludes the first execution.",
        "Count the first execution; dead-letter when a retryable failure occurs on attempt 3.",
    ),
    CheckSpec(
        "T3-R03", "Restart preserves completed-job dedup and pending attempt counts",
        "resilience", 8, "critical", "data_integrity_idempotency",
        "Dedup or attempt state lives in memory or is reset on resubmission after restart.",
        "Keep all job state in the store and read it on every submit and run.",
    ),
)
# fmt: on

CHECKS: dict[str, Callable[[ModuleType, Path, Recorder], None]] = {
    "T3-C01": check_completes_once,
    "T3-C02": check_rejects_before_effect,
    "T3-C03": check_permanent_not_retried,
    "T3-C04": check_changed_payload_conflicts,
    "T3-S01": check_duplicate_delivery,
    "T3-S02": check_dead_letter_safe,
    "T3-S03": check_bounded_redelivery,
    "T3-R01": check_retry_schedule,
    "T3-R02": check_exhaustion,
    "T3-R03": check_restart_persistence,
}
