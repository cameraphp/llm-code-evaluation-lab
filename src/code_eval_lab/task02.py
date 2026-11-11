"""Task 02 oracle: multi-tenant document authorization (contract `task-02/v1`).

Evaluator-side only. See examples/task-02-tenant-authorization/TASK.md. Evidence records sensitive
*categories*, never sensitive values, so reports cannot repeat a leak.
"""

from __future__ import annotations

import contextlib
import copy
import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from code_eval_lab.scoring import CandidateViolation, CheckSpec, Recorder

TASK_ID = "task-02"
TITLE = "Multi-tenant document authorization"
VERSION = "task-02/v1"

PUBLIC_FIELDS = ["document_id", "status", "title"]
AUDIT_KEYS = frozenset({"operation", "outcome", "reason", "subject", "document_id"})
NORTH_IDS = ["doc-n-001", "doc-n-002"]
SOUTH_IDS = ["doc-s-001", "doc-s-002"]


@dataclass(frozen=True)
class Principal:
    """Immutable authenticated principal produced by the trusted identity lookup."""

    subject: str
    tenant_id: str
    roles: frozenset[str]


PRINCIPALS = {
    "tok-north-reader": Principal("user-n-reader", "tenant-north", frozenset({"documents:read"})),
    "tok-south-reader": Principal("user-s-reader", "tenant-south", frozenset({"documents:read"})),
    "tok-north-viewer": Principal("user-n-viewer", "tenant-north", frozenset({"profile:read"})),
}

# document_id, tenant_id, title, status, internal_notes, owner_contact (all fictional)
DOCUMENTS = [
    (
        "doc-n-001",
        "tenant-north",
        "North roadmap draft",
        "open",
        "SECRET-north-note-1",
        "owner1@north.example",
    ),
    (
        "doc-n-002",
        "tenant-north",
        "North budget memo",
        "closed",
        "SECRET-north-note-2",
        "owner2@north.example",
    ),
    (
        "doc-s-001",
        "tenant-south",
        "South pricing sheet",
        "open",
        "SECRET-south-note-1",
        "owner1@south.example",
    ),
    ("doc-s-002", "tenant-south", "South vendor list", "open", "SECRET-south-note-2", "owner2@south.example"),
]

# Category -> markers, from the north callers' point of view. Only category names reach reports.
SENSITIVE_MARKERS = {
    "bearer_token": ("tok-",),
    "internal_notes": ("SECRET-",),
    "other_tenant_id": ("tenant-south",),
    "other_tenant_title": ("South pricing sheet", "South vendor list"),
    "owner_contact": ("@north.example", "@south.example"),
}

SCHEMA = """
CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    internal_notes TEXT NOT NULL,
    owner_contact TEXT NOT NULL
);
"""


class IdentityUnavailable(Exception):
    """Raised by the harness identity lookup to simulate a directory outage."""


def exposed(value: Any) -> list[str]:
    text = json.dumps(value, sort_keys=True, default=repr)
    return sorted(cat for cat, markers in SENSITIVE_MARKERS.items() if any(m in text for m in markers))


def seed_store(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)", DOCUMENTS)
        conn.commit()
    finally:
        conn.close()


def trusted_identity(token: str) -> Principal | None:
    return PRINCIPALS.get(token)


def unavailable_identity(token: str) -> Principal | None:
    raise IdentityUnavailable("identity directory timeout")


def make_request(
    operation: str,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    all_headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    all_headers.update(headers or {})
    return {"operation": operation, "headers": all_headers, "params": dict(params or {})}


def get_doc(document_id: Any, token: str | None, **kw: Any) -> dict[str, Any]:
    params = {"document_id": document_id, **kw.pop("params", {})}
    return make_request("get_document", token, params, **kw)


def list_docs(token: str | None, **kw: Any) -> dict[str, Any]:
    return make_request("list_documents", token, **kw)


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

    def item_ids(self) -> list[Any] | None:
        items = self.body.get("items")
        if not isinstance(items, list):
            return None
        return [item.get("document_id") if isinstance(item, dict) else None for item in items]

    def items_public_only(self) -> bool:
        items = self.body.get("items")
        return isinstance(items, list) and all(
            isinstance(i, dict) and sorted(i) == PUBLIC_FIELDS for i in items
        )

    def carries_data(self) -> bool:
        return "items" in self.body or "document_id" in self.body or "title" in self.body


def call(service: Any, request: Any) -> Outcome:
    try:
        response = service.handle(copy.deepcopy(request))
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


@contextlib.contextmanager
def open_service(
    module: ModuleType,
    workdir: Path,
    audit_events: list[Any] | None = None,
    identity: Callable[[str], Principal | None] = trusted_identity,
) -> Iterator[Any]:
    db = workdir / "documents.db"
    if not db.exists():
        seed_store(db)
    sink = audit_events if audit_events is not None else []
    try:
        service = module.DocumentService(str(db), identity, sink.append)
    except Exception as exc:
        raise CandidateViolation(
            "construct", "DocumentService(...) constructs without raising", f"raised {type(exc).__name__}"
        ) from exc
    try:
        yield service
    finally:
        with contextlib.suppress(Exception):
            service.close()


def redacted(body: dict[str, Any]) -> dict[str, Any]:
    """Evidence-safe view of an unexpected body: key names and sensitive categories, no values."""
    return {"keys": sorted(body), "exposed_categories": exposed(body)}


def _expect_error(rec: Recorder, name: str, label: str, outcome: Outcome, status: int, code: str) -> None:
    expected = {"error": code}
    rec.expect(f"{name}_status", f"{label} returns {status}", status, outcome.observed)
    rec.record(
        f"{name}_body",
        f"{label} body is exactly {{error: {code}}}",
        expected,
        outcome.body if outcome.body == expected else redacted(outcome.body),
        outcome.body == expected,
    )


# --- checks ------------------------------------------------------------------------------


def check_own_read(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    with open_service(module, workdir) as service:
        out = call(service, get_doc("doc-n-001", "tok-north-reader"))
    rec.expect("status", "permitted reader gets own document: 200", 200, out.observed)
    rec.expect("fields", "body has exactly the public fields", PUBLIC_FIELDS, sorted(out.body))
    rec.expect(
        "values",
        "public values match the stored row",
        ["doc-n-001", "open", "North roadmap draft"],
        [out.body.get(f) for f in PUBLIC_FIELDS],
    )
    rec.expect("exposed_categories", "no sensitive categories in the body", [], exposed(out.body))


def check_collection_scope(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    with open_service(module, workdir) as service:
        north = call(service, list_docs("tok-north-reader"))
        south = call(service, list_docs("tok-south-reader"))
    rec.expect("north_status", "north list returns 200", 200, north.observed)
    rec.expect("north_ids", "north list contains only north documents, sorted", NORTH_IDS, north.item_ids())
    rec.expect("north_public_only", "north items carry only public fields", True, north.items_public_only())
    rec.expect("north_exposed", "north list has no sensitive categories", [], exposed(north.body))
    rec.expect("south_ids", "south list contains only south documents, sorted", SOUTH_IDS, south.item_ids())


def check_authentication(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    variants = {
        "no_header": {},
        "wrong_scheme": {"Authorization": "Basic dG9rLW5vcnRoLXJlYWRlcg=="},
        "empty_token": {"Authorization": "Bearer "},
        "unknown_token": {"Authorization": "Bearer tok-unknown"},
    }
    with open_service(module, workdir) as service:
        outcomes = []
        for name, headers in variants.items():
            outcomes.append((f"{name}_get", call(service, get_doc("doc-n-001", None, headers=headers))))
            outcomes.append((f"{name}_list", call(service, list_docs(None, headers=headers))))
        valid = call(service, get_doc("doc-n-001", "tok-north-reader"))
    for name, outcome in outcomes:
        _expect_error(rec, name, f"unauthenticated '{name}'", outcome, 401, "unauthenticated")
    rec.expect(
        "valid_token_status", "a valid token is authenticated (distinct from 401)", 200, valid.observed
    )


def check_function_permission(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    with open_service(module, workdir) as service:
        cases = [
            ("get", call(service, get_doc("doc-n-001", "tok-north-viewer"))),
            ("list", call(service, list_docs("tok-north-viewer"))),
            ("get_missing", call(service, get_doc("doc-x-999", "tok-north-viewer"))),
        ]
    for name, outcome in cases:
        _expect_error(rec, name, f"caller without documents:read ({name})", outcome, 403, "forbidden")
        rec.expect(
            f"{name}_no_data", f"denied {name} carries no document data", False, outcome.carries_data()
        )


def check_object_level_access(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    with open_service(module, workdir) as service:
        cross = call(service, get_doc("doc-s-001", "tok-north-reader"))
        missing = call(service, get_doc("doc-x-999", "tok-north-reader"))
        reverse = call(service, get_doc("doc-n-002", "tok-south-reader"))
    _expect_error(rec, "cross_tenant", "north reader requesting a south document", cross, 404, "not_found")
    _expect_error(rec, "nonexistent", "nonexistent document", missing, 404, "not_found")
    rec.expect(
        "indistinguishable",
        "cross-tenant and nonexistent responses are identical",
        True,
        (cross.observed, cross.body) == (missing.observed, missing.body),
    )
    rec.expect(
        "cross_tenant_exposed", "cross-tenant response has no south categories", [], exposed(cross.body)
    )
    rec.expect(
        "reverse_status", "south reader requesting a north document returns 404", 404, reverse.observed
    )
    rec.expect("reverse_no_data", "reverse response carries no document data", False, reverse.carries_data())


def check_client_scope_ignored(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    spoof = {"X-Tenant-Id": "tenant-south", "X-Roles": "documents:read,admin", "X-User": "user-s-reader"}
    with open_service(module, workdir) as service:
        list_header = call(service, list_docs("tok-north-reader", headers=spoof))
        list_param = call(service, list_docs("tok-north-reader", params={"tenant_id": "tenant-south"}))
        get_spoofed = call(
            service,
            get_doc("doc-s-001", "tok-north-reader", headers=spoof, params={"tenant_id": "tenant-south"}),
        )
        viewer_get = call(service, get_doc("doc-n-001", "tok-north-viewer", headers=spoof))
    rec.expect(
        "list_header_ids",
        "spoofed tenant header does not change list scope",
        NORTH_IDS,
        list_header.item_ids(),
    )
    rec.expect(
        "list_param_ids", "tenant_id param does not change list scope", NORTH_IDS, list_param.item_ids()
    )
    rec.expect("get_spoofed_status", "spoofed get of a south document returns 404", 404, get_spoofed.observed)
    rec.expect(
        "get_spoofed_exposed", "spoofed get exposes no south categories", [], exposed(get_spoofed.body)
    )
    rec.expect("viewer_get_status", "spoofed X-Roles does not grant documents:read", 403, viewer_get.observed)


def check_safe_denials(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    events: list[Any] = []
    with open_service(module, workdir, events) as service:
        denials = [
            call(service, get_doc("doc-s-001", None)),
            call(service, get_doc("doc-s-001", None, headers={"Authorization": "Bearer tok-unknown"})),
            call(service, get_doc("doc-s-001", "tok-north-viewer")),
            call(service, get_doc("doc-s-001", "tok-north-reader")),
            call(service, get_doc("doc-x-999", "tok-north-reader")),
            call(service, get_doc("doc-s-001' OR '1'='1", "tok-north-reader")),
        ]
    error_codes = {"unauthenticated", "forbidden", "not_found", "invalid_request"}
    rec.expect(
        "bodies_exact_errors",
        "every denial body is exactly {error: <code>} from the contract vocabulary",
        True,
        all(sorted(d.body) == ["error"] and d.body.get("error") in error_codes for d in denials),
    )
    rec.expect(
        "bodies_exposed",
        "denial bodies contain no sensitive categories",
        [],
        exposed([d.body for d in denials]),
    )
    rec.expect(
        "audit_shape",
        "audit events are dicts with allowed keys and str/None values",
        True,
        all(
            isinstance(e, dict)
            and set(e) <= AUDIT_KEYS
            and all(v is None or isinstance(v, str) for v in e.values())
            for e in events
        ),
    )
    rec.expect("audit_exposed", "audit events contain no sensitive categories", [], exposed(events))


def check_malformed_requests(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    token = "tok-north-reader"
    cases: list[tuple[str, Any]] = [
        ("not_an_object", "GET /documents/doc-n-001"),
        ("unknown_operation", make_request("delete_document", token, {"document_id": "doc-n-001"})),
        ("missing_document_id", make_request("get_document", token, {})),
        ("non_string_id", get_doc(101, token)),
        ("overlong_id", get_doc("doc-" + "a" * 80, token)),
        ("quote_injection_id", get_doc("doc-n-001' OR '1'='1", token)),
        ("traversal_id", get_doc("../doc-s-001", token)),
    ]
    with open_service(module, workdir) as service:
        outcomes = [(name, call(service, request)) for name, request in cases]
    for name, outcome in outcomes:
        _expect_error(rec, name, f"malformed request '{name}'", outcome, 400, "invalid_request")
    rec.expect(
        "no_data",
        "no malformed request returns document data",
        False,
        any(o.carries_data() for _, o in outcomes),
    )


def check_identity_outage(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    with open_service(module, workdir, identity=unavailable_identity) as service:
        get_out = call(service, get_doc("doc-n-001", "tok-north-reader"))
        list_out = call(service, list_docs("tok-north-reader"))
    _expect_error(rec, "get", "get during identity outage", get_out, 503, "identity_unavailable")
    _expect_error(rec, "list", "list during identity outage", list_out, 503, "identity_unavailable")


# --- manifest ----------------------------------------------------------------------------
# Positional fields: id, title, category, weight, severity, taxonomy, suspected_cause, remediation.
# fmt: off
MANIFEST: tuple[CheckSpec, ...] = (
    CheckSpec(
        "T2-C01", "Permitted caller reads own document with only public fields",
        "correctness", 12, "major", "logic_correctness",
        "The read path returns the whole stored row instead of a field allowlist.",
        "Select and return only document_id, title and status.",
    ),
    CheckSpec(
        "T2-C02", "Collection reads contain only the caller's tenant rows",
        "correctness", 10, "critical", "authorization_security",
        "The list query is not scoped by the principal's tenant.",
        "Filter list queries by principal.tenant_id and project the public fields.",
    ),
    CheckSpec(
        "T2-C03", "Unauthenticated callers are denied with 401",
        "correctness", 8, "critical", "authorization_security",
        "Credential parsing accepts malformed headers, or unknown tokens are not rejected.",
        "Accept only 'Bearer <token>' resolved by the identity lookup; otherwise return 401.",
    ),
    CheckSpec(
        "T2-C04", "Authenticated callers without documents:read are denied with 403",
        "correctness", 10, "critical", "authorization_security",
        "The permission check is missing for at least one operation (function-level authorization).",
        "Check the role required by every operation before any data access.",
    ),
    CheckSpec(
        "T2-S01", "Another tenant's document ID cannot be read (BOLA/IDOR)",
        "safety_integrity", 12, "critical", "authorization_security",
        "The object lookup is keyed by document_id only, without the principal's tenant.",
        "Scope every object lookup by tenant and return the shared 404 for out-of-scope IDs.",
    ),
    CheckSpec(
        "T2-S02", "Client-supplied tenant, role or user hints cannot change scope",
        "safety_integrity", 10, "critical", "authorization_security",
        "Request headers or params are consulted when deriving tenant or roles.",
        "Derive tenant and roles only from the principal returned by the identity lookup.",
    ),
    CheckSpec(
        "T2-S03", "Denials and audit events expose no other-tenant details or tokens",
        "safety_integrity", 8, "critical", "authorization_security",
        "Denial paths serialize the raw request or the stored record into responses or audit events.",
        "Return exact error codes and audit only operation, outcome, reason, subject and document_id.",
    ),
    CheckSpec(
        "T2-R01", "Malformed requests are rejected with 400 without data or exceptions",
        "resilience", 10, "major", "logic_correctness",
        "Request shape or document_id format is not validated before use.",
        "Validate request shape and document_id format and return 400; keep it separate from authorization.",
    ),
    CheckSpec(
        "T2-R02", "Identity lookup outage fails closed with 503",
        "resilience", 10, "critical", "authorization_security",
        "Identity lookup exceptions propagate or are treated as an anonymous or permitted caller.",
        "Catch identity lookup failures and return 503 without touching the store.",
    ),
)
# fmt: on

CHECKS: dict[str, Callable[[ModuleType, Path, Recorder], None]] = {
    "T2-C01": check_own_read,
    "T2-C02": check_collection_scope,
    "T2-C03": check_authentication,
    "T2-C04": check_function_permission,
    "T2-S01": check_object_level_access,
    "T2-S02": check_client_scope_ignored,
    "T2-S03": check_safe_denials,
    "T2-R01": check_malformed_requests,
    "T2-R02": check_identity_outage,
}
