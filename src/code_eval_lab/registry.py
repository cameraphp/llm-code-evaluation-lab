"""Allowlisted tasks and controlled candidate fixtures.

Callers select IDs from these tables only. No path, code string, URL or module name is ever
accepted from input. Each fixture is pinned by SHA-256 and refused if its content changes.

Importing a fixture executes its code in this process. That is acceptable only for
owner-reviewed fixtures. It is NOT a sandbox and must never be used for untrusted code.
"""

from __future__ import annotations

import hashlib
import importlib.util
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from code_eval_lab import task01, task02, task03
from code_eval_lab.scoring import CheckSpec, Recorder

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = PROJECT_ROOT / "fixtures"

PROVENANCE = (
    "Controlled lab fixture written for this project with AI assistance; pending owner "
    "review. Not output from a measured LLM experiment."
)


class RegistryError(Exception):
    """Unknown task or candidate ID (a selection error; nothing was executed)."""


class FixtureError(Exception):
    """An allowlisted fixture could not be verified or loaded (setup error)."""


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    version: str
    manifest: tuple[CheckSpec, ...]
    checks: Mapping[str, Callable[[ModuleType, Path, Recorder], None]]
    entrypoint: str  # attribute the fixture must expose
    stage: int  # lab stage that introduced the task


@dataclass(frozen=True)
class Candidate:
    task_id: str
    id: str
    relative_path: str
    sha256: str


TASKS: dict[str, Task] = {
    t.id: t
    for t in (
        Task(task01.TASK_ID, task01.TITLE, task01.VERSION, task01.MANIFEST, task01.CHECKS, "OrderService", 1),
        Task(
            task02.TASK_ID, task02.TITLE, task02.VERSION, task02.MANIFEST, task02.CHECKS, "DocumentService", 2
        ),
        Task(task03.TASK_ID, task03.TITLE, task03.VERSION, task03.MANIFEST, task03.CHECKS, "JobWorker", 2),
    )
}

_FIXTURE_DIRS = {
    "task-01": "fixtures/task-01-api-idempotency",
    "task-02": "fixtures/task-02-tenant-authorization",
    "task-03": "fixtures/task-03-agent-jobs",
}
CANDIDATES: dict[tuple[str, str], Candidate] = {
    (c.task_id, c.id): c
    for c in (
        Candidate(
            "task-01",
            "reference",
            f"{_FIXTURE_DIRS['task-01']}/reference.py",
            "72d03a29e48716bd1ed1e12bdedb095f8291d16115fa91f1e9c460093c615de6",
        ),
        Candidate(
            "task-01",
            "flawed",
            f"{_FIXTURE_DIRS['task-01']}/flawed.py",
            "b8d805a66c07d18d9cdea643fe0339830a3db08b3e9d2ece6c652b2b36c1ee35",
        ),
        Candidate(
            "task-01",
            "partial",
            f"{_FIXTURE_DIRS['task-01']}/partial.py",
            "1d306ffd2d334ec811fdf8fc93d76d613e8d94105310f95b25e197da8477b68e",
        ),
        Candidate(
            "task-02",
            "reference",
            f"{_FIXTURE_DIRS['task-02']}/reference.py",
            "ee4f784a54302253f9591f1ef1993a37cd96522f215a13fab424d20db0d13a23",
        ),
        Candidate(
            "task-02",
            "flawed",
            f"{_FIXTURE_DIRS['task-02']}/flawed.py",
            "ae5c9d4c3b57af96e57281e0fc7acd705d67bca463fbc8168fce1e1256418193",
        ),
        Candidate(
            "task-02",
            "partial",
            f"{_FIXTURE_DIRS['task-02']}/partial.py",
            "7497d8ac9271a021db15cf9864828131e0f5837482f92c4817d3928854339101",
        ),
        Candidate(
            "task-03",
            "reference",
            f"{_FIXTURE_DIRS['task-03']}/reference.py",
            "ec4e69f300b9bb237a8fa7c21b844fa8d3ca8752d6c675c11c3c3e66a4d08054",
        ),
        Candidate(
            "task-03",
            "flawed",
            f"{_FIXTURE_DIRS['task-03']}/flawed.py",
            "1a2428df8b822be26a2ffa2696694a3bd5f9094cec73ef0c1f634571084711ee",
        ),
        Candidate(
            "task-03",
            "partial",
            f"{_FIXTURE_DIRS['task-03']}/partial.py",
            "4063022b3b557a81cbc7b26192ad532a7f911ffdd1efd0f03d5542023d20db67",
        ),
    )
}


def get_task(task_id: str) -> Task:
    try:
        return TASKS[task_id]
    except (KeyError, TypeError):
        raise RegistryError(f"unknown task ID {task_id!r}; allowed: {sorted(TASKS)}") from None


def get_candidate(task_id: str, candidate_id: str) -> Candidate:
    get_task(task_id)
    try:
        return CANDIDATES[(task_id, candidate_id)]
    except (KeyError, TypeError):
        allowed = sorted(cid for tid, cid in CANDIDATES if tid == task_id)
        raise RegistryError(f"unknown candidate ID {candidate_id!r}; allowed: {allowed}") from None


def fixture_path(candidate: Candidate) -> Path:
    path = (PROJECT_ROOT / candidate.relative_path).resolve()
    if not path.is_relative_to(FIXTURES_DIR.resolve()):
        raise FixtureError(f"fixture for {candidate.id!r} is outside the fixtures directory")
    return path


def fixture_digest(path: Path) -> str:
    """SHA-256 of the file with CRLF normalised to LF (stable across checkouts)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def digest_status(candidate: Candidate) -> str:
    path = fixture_path(candidate)
    if not path.is_file():
        return "MISSING"
    return "OK" if fixture_digest(path) == candidate.sha256 else "MISMATCH"


def load_candidate(candidate: Candidate) -> ModuleType:
    path = fixture_path(candidate)
    if not path.is_file():
        raise FixtureError(f"fixture file missing: {candidate.relative_path}")
    if fixture_digest(path) != candidate.sha256:
        raise FixtureError(
            f"fixture digest mismatch for {candidate.task_id}/{candidate.id}; review the change "
            "and re-pin it in registry.py before executing it"
        )
    name = f"code_eval_fixture_{candidate.task_id.replace('-', '_')}_{candidate.id}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FixtureError(f"cannot build an import spec for {candidate.relative_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise FixtureError(f"fixture import failed: {type(exc).__name__}") from exc
    entrypoint = get_task(candidate.task_id).entrypoint
    if not callable(getattr(module, entrypoint, None)):
        raise FixtureError(f"fixture does not expose the {entrypoint} interface")
    return module
