"""Task 02 candidate `reference`: multi-tenant document reads (controlled lab fixture)."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

DOCUMENT_ID = re.compile(r"doc-[a-z0-9-]{1,40}")
REQUIRED_ROLE = {"get_document": "documents:read", "list_documents": "documents:read"}


def _error(status: int, code: str) -> dict[str, Any]:
    return {"status": status, "body": {"error": code}}


class DocumentService:
    def __init__(self, db_path: str, identity: Callable[[str], Any], audit: Callable[[dict], None]) -> None:
        self._conn = sqlite3.connect(f"{Path(db_path).as_uri()}?mode=ro", uri=True)
        self._identity = identity
        self._audit = audit

    def close(self) -> None:
        self._conn.close()

    def _deny(
        self, status: int, code: str, operation: str | None, subject: str | None, document_id: str | None
    ) -> dict[str, Any]:
        self._audit(
            {
                "operation": operation,
                "outcome": "denied",
                "reason": code,
                "subject": subject,
                "document_id": document_id,
            }
        )
        return _error(status, code)

    def _authenticate(self, headers: dict[str, Any]) -> Any:
        """Authentication: resolve who is calling. Returns a principal or None."""
        value = headers.get("Authorization")
        if not isinstance(value, str) or not value.startswith("Bearer "):
            return None
        token = value[len("Bearer ") :]
        return self._identity(token) if token else None

    def handle(self, request: Any) -> dict[str, Any]:
        if not (
            isinstance(request, dict)
            and isinstance(request.get("operation"), str)
            and isinstance(request.get("headers"), dict)
            and isinstance(request.get("params"), dict)
        ):
            return self._deny(400, "invalid_request", None, None, None)
        operation, params = request["operation"], request["params"]
        known_operation = operation if operation in REQUIRED_ROLE else None
        raw_id = params.get("document_id")
        safe_id = raw_id if isinstance(raw_id, str) and DOCUMENT_ID.fullmatch(raw_id) else None

        try:
            principal = self._authenticate(request["headers"])
        except Exception:
            return self._deny(503, "identity_unavailable", known_operation, None, safe_id)
        if principal is None:
            return self._deny(401, "unauthenticated", known_operation, None, safe_id)
        if known_operation is None:
            return self._deny(400, "invalid_request", None, principal.subject, None)
        # Authorization (function level): may this principal perform the operation at all?
        if REQUIRED_ROLE[operation] not in principal.roles:
            return self._deny(403, "forbidden", operation, principal.subject, safe_id)

        if operation == "list_documents":
            rows = self._conn.execute(
                "SELECT document_id, title, status FROM documents WHERE tenant_id = ? ORDER BY document_id",
                (principal.tenant_id,),
            ).fetchall()
            items = [{"document_id": d, "title": t, "status": s} for d, t, s in rows]
            return {"status": 200, "body": {"items": items}}

        # Input validation, not authorization: a well-formed ID grants nothing by itself.
        if safe_id is None:
            return self._deny(400, "invalid_request", operation, principal.subject, None)
        # Authorization (object level): the lookup is scoped to the principal's tenant.
        row = self._conn.execute(
            "SELECT document_id, title, status FROM documents WHERE document_id = ? AND tenant_id = ?",
            (safe_id, principal.tenant_id),
        ).fetchone()
        if row is None:
            return self._deny(404, "not_found", operation, principal.subject, safe_id)
        return {"status": 200, "body": {"document_id": row[0], "title": row[1], "status": row[2]}}
