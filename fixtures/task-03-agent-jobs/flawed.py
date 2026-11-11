"""Task 03 candidate `flawed`: agent-proposed background jobs (controlled lab fixture)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

MAX_ATTEMPTS = 3
BACKOFF_S = (10, 30, 90)
TOOLS = {"send_notice": ("recipient_id", "template"), "archive_document": ("document_id",)}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_key TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    args_json TEXT NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    next_run_at INTEGER,
    last_error TEXT,
    last_error_detail TEXT
);
"""


def invalid_field(proposal: Any) -> str | None:
    if not isinstance(proposal, dict):
        return "proposal"
    key = proposal.get("job_key")
    if not isinstance(key, str) or not key.startswith("job-") or " " in key:
        return "job_key"
    tool = proposal.get("tool")
    if not isinstance(tool, str) or tool not in TOOLS:
        return "tool"
    args = proposal.get("args")
    if not isinstance(args, dict):
        return "args"
    for name in TOOLS[tool]:
        if not isinstance(args.get(name), str):
            return f"args.{name}"
    return None


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
        key = proposal["job_key"]
        # Upsert keeps the newest version of the job the agent asked for.
        self._conn.execute(
            "INSERT OR REPLACE INTO jobs (job_key, tool, args_json, state, attempts, next_run_at) "
            "VALUES (?, ?, ?, 'queued', 0, ?)",
            (key, proposal["tool"], json.dumps(proposal["args"]), self._clock.now()),
        )
        return {"status": 202, "body": {"job_key": key, "state": "queued"}}

    def run_due(self) -> int:
        now = self._clock.now()
        due = self._conn.execute(
            "SELECT job_key, tool, args_json, attempts FROM jobs "
            "WHERE state IN ('queued', 'retry_scheduled') AND next_run_at <= ? ORDER BY next_run_at, job_key",
            (now,),
        ).fetchall()
        for key, tool, args_json, attempts in due:
            attempt = attempts + 1
            self._conn.execute("UPDATE jobs SET attempts = ? WHERE job_key = ?", (attempt, key))
            try:
                self._effects.invoke(tool, json.loads(args_json), key)
            except Exception as exc:
                detail = f"{type(exc).__name__}: {exc}"  # kept for debugging
                if not getattr(exc, "retryable", False):
                    self._fail(key, "dead_letter", None, "permanent_error", detail)
                elif attempt <= MAX_ATTEMPTS:
                    delay = BACKOFF_S[min(attempt, len(BACKOFF_S)) - 1]
                    self._fail(key, "retry_scheduled", now + delay, "transient_error", detail)
                else:
                    self._fail(key, "dead_letter", None, "transient_exhausted", detail)
            else:
                self._conn.execute(
                    "UPDATE jobs SET state = 'succeeded', next_run_at = NULL, last_error = NULL "
                    "WHERE job_key = ?",
                    (key,),
                )
        return len(due)

    def _fail(self, key: str, state: str, next_run_at: int | None, reason: str, detail: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET state = ?, next_run_at = ?, last_error = ?, last_error_detail = ? "
            "WHERE job_key = ?",
            (state, next_run_at, reason, detail, key),
        )
