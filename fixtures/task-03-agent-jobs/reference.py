"""Task 03 candidate `reference`: agent-proposed background jobs (controlled lab fixture)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any

MAX_ATTEMPTS = 3  # includes the first execution
BACKOFF_S = (10, 30)  # delay after failed attempt 1 and 2
JOB_KEY = re.compile(r"job-[a-z0-9-]{4,40}")
AGENT_ID = re.compile(r"agent-[a-z0-9-]{1,32}")
PROPOSAL_FIELDS = frozenset({"job_key", "tool", "args", "proposed_by"})
TOOLS: dict[str, dict[str, Any]] = {
    "send_notice": {"recipient_id": re.compile(r"usr-\d{3}"), "template": frozenset({"welcome", "reminder"})},
    "archive_document": {"document_id": re.compile(r"doc-\d{3}")},
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    args_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    next_run_at INTEGER,
    last_error TEXT
);
"""


def _arg_ok(rule: Any, value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value in rule if isinstance(rule, frozenset) else rule.fullmatch(value) is not None


def invalid_field(proposal: Any) -> str | None:
    """Policy gate: return the first invalid field, or None when the proposal is allowed."""
    if not isinstance(proposal, dict) or set(proposal) != PROPOSAL_FIELDS:
        return "proposal"
    if not isinstance(proposal["job_key"], str) or not JOB_KEY.fullmatch(proposal["job_key"]):
        return "job_key"
    if not isinstance(proposal["proposed_by"], str) or not AGENT_ID.fullmatch(proposal["proposed_by"]):
        return "proposed_by"
    tool = proposal["tool"]
    if not isinstance(tool, str) or tool not in TOOLS:
        return "tool"
    schema, args = TOOLS[tool], proposal["args"]
    if not isinstance(args, dict) or set(args) != set(schema):
        return "args"
    for name, rule in schema.items():
        if not _arg_ok(rule, args[name]):
            return f"args.{name}"
    return None


def fingerprint(tool: str, args: dict[str, str]) -> str:
    canonical = json.dumps({"tool": tool, "args": args}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class JobWorker:
    def __init__(self, db_path: str, effects: Any, clock: Any) -> None:
        self._conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
        self._conn.executescript(SCHEMA)
        self._effects = effects
        self._clock = clock

    def close(self) -> None:
        self._conn.close()

    def submit(self, proposal: Any) -> dict[str, Any]:
        field = invalid_field(proposal)
        if field is not None:
            return {"status": 422, "body": {"error": "invalid_proposal", "field": field}}
        key, tool, args = proposal["job_key"], proposal["tool"], proposal["args"]
        job_fp = fingerprint(tool, args)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT fingerprint, state FROM jobs WHERE job_key = ?", (key,)
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO jobs (job_key, tool, args_json, fingerprint, state, attempts, next_run_at) "
                    "VALUES (?, ?, ?, ?, 'queued', 0, ?)",
                    (key, tool, json.dumps(args, sort_keys=True), job_fp, self._clock.now()),
                )
                response = {"status": 202, "body": {"job_key": key, "state": "queued"}}
            elif row[0] != job_fp:
                response = {"status": 409, "body": {"error": "job_key_conflict"}}
            else:
                response = {"status": 200, "body": {"job_key": key, "state": row[1], "duplicate": True}}
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return response

    def run_due(self) -> int:
        now = self._clock.now()
        due = self._conn.execute(
            "SELECT job_key, tool, args_json, attempts FROM jobs "
            "WHERE state IN ('queued', 'retry_scheduled') AND next_run_at <= ? "
            "ORDER BY next_run_at, job_key",
            (now,),
        ).fetchall()
        made = 0
        for key, tool, args_json, attempts in due:
            if attempts >= MAX_ATTEMPTS:  # an earlier attempt's outcome was never recorded
                self._finish(key, "dead_letter", "transient_exhausted")
                continue
            attempt = attempts + 1
            # Persist the attempt before the effect so a crash cannot reset the bound.
            claimed = self._conn.execute(
                "UPDATE jobs SET attempts = ? WHERE job_key = ? AND attempts = ?", (attempt, key, attempts)
            ).rowcount
            if claimed != 1:
                continue
            made += 1
            try:
                self._effects.invoke(tool, json.loads(args_json), key)
            except Exception as exc:
                if getattr(exc, "retryable", False) is not True:
                    self._finish(key, "dead_letter", "permanent_error")
                elif attempt >= MAX_ATTEMPTS:
                    self._finish(key, "dead_letter", "transient_exhausted")
                else:
                    self._conn.execute(
                        "UPDATE jobs SET state = 'retry_scheduled', next_run_at = ?, "
                        "last_error = 'transient_error' WHERE job_key = ?",
                        (now + BACKOFF_S[attempt - 1], key),
                    )
            else:
                self._finish(key, "succeeded", None)
        return made

    def _finish(self, key: str, state: str, reason: str | None) -> None:
        self._conn.execute(
            "UPDATE jobs SET state = ?, next_run_at = NULL, last_error = ? WHERE job_key = ?",
            (state, reason, key),
        )
