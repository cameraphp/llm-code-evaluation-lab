"""Task 02 candidate `flawed`: multi-tenant document reads (controlled lab fixture)."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from typing import Any

# The candidate's own label for itself. The evaluator must ignore it.
CANDIDATE_LABEL = "reference"

DOCUMENT_ID = re.compile(r"doc-[a-z0-9-]{1,40}")
OPERATIONS = ("get_document", "list_documents")


class DocumentService:
    def __init__(self, db_path: str, identity: Callable[[str], Any], audit: Callable[[dict], None]) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._identity = identity
        self._audit = audit

    def close(self) -> None:
        self._conn.close()

    def _deny(self, status: int, code: str, request: Any) -> dict[str, Any]:
        # Keep the full request so support can reproduce problems.
        self._audit({"outcome": "denied", "reason": code, "request": request})
        return {"status": status, "body": {"error": code}}

    def handle(self, request: Any) -> dict[str, Any]:
        if not (
            isinstance(request, dict)
            and isinstance(request.get("operation"), str)
            and isinstance(request.get("headers"), dict)
            and isinstance(request.get("params"), dict)
        ):
            return self._deny(400, "invalid_request", request)
        headers, params = request["headers"], request["params"]
        auth = headers.get("Authorization")
        if not isinstance(auth, str) or not auth.startswith("Bearer ") or auth == "Bearer ":
            return self._deny(401, "unauthenticated", request)
        try:
            principal = self._identity(auth[len("Bearer ") :])
        except Exception:
            return self._deny(503, "identity_unavailable", request)
        if principal is None:
            return self._deny(401, "unauthenticated", request)
        if request["operation"] not in OPERATIONS:
            return self._deny(400, "invalid_request", request)
        if "documents:read" not in principal.roles:
            return self._deny(403, "forbidden", request)

        if request["operation"] == "list_documents":
            # Support tooling may pass a tenant explicitly.
            tenant = params.get("tenant_id") or headers.get("X-Tenant-Id") or principal.tenant_id
            rows = self._conn.execute(
                "SELECT document_id, title, status FROM documents WHERE tenant_id = ? ORDER BY document_id",
                (tenant,),
            ).fetchall()
            return {"status": 200, "body": {"items": [dict(row) for row in rows]}}

        document_id = params.get("document_id")
        if not isinstance(document_id, str) or not DOCUMENT_ID.fullmatch(document_id):
            return self._deny(400, "invalid_request", request)
        row = self._conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
        if row is None:
            return self._deny(404, "not_found", request)
        return {"status": 200, "body": dict(row)}
