"""Task 02 candidate `partial`: multi-tenant document reads (controlled lab fixture)."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

DOCUMENT_ID = re.compile(r"doc-[a-z0-9-]{1,40}")
OPERATIONS = ("get_document", "list_documents")


class DocumentService:
    def __init__(self, db_path: str, identity: Callable[[str], Any], audit: Callable[[dict], None]) -> None:
        self._conn = sqlite3.connect(f"{Path(db_path).as_uri()}?mode=ro", uri=True)
        self._identity = identity
        self._audit = audit

    def close(self) -> None:
        self._conn.close()

    def _deny(self, status: int, code: str, subject: str | None = None) -> dict[str, Any]:
        self._audit({"outcome": "denied", "reason": code, "subject": subject})
        return {"status": status, "body": {"error": code}}

    def handle(self, request: Any) -> dict[str, Any]:
        if not (
            isinstance(request, dict)
            and isinstance(request.get("operation"), str)
            and isinstance(request.get("headers"), dict)
            and isinstance(request.get("params"), dict)
        ):
            return self._deny(400, "invalid_request")
        auth = request["headers"].get("Authorization")
        if not isinstance(auth, str) or not auth.startswith("Bearer ") or auth == "Bearer ":
            return self._deny(401, "unauthenticated")
        try:
            principal = self._identity(auth[len("Bearer ") :])
        except Exception:
            return self._deny(503, "identity_unavailable")
        if principal is None:
            return self._deny(401, "unauthenticated")
        operation = request["operation"]
        if operation not in OPERATIONS:
            return self._deny(400, "invalid_request", principal.subject)

        if operation == "list_documents":
            rows = self._conn.execute(
                "SELECT document_id, title, status FROM documents WHERE tenant_id = ? ORDER BY document_id",
                (principal.tenant_id,),
            ).fetchall()
            return {
                "status": 200,
                "body": {"items": [{"document_id": d, "title": t, "status": s} for d, t, s in rows]},
            }

        if "documents:read" not in principal.roles:
            return self._deny(403, "forbidden", principal.subject)
        document_id = request["params"].get("document_id")
        if not isinstance(document_id, str) or not DOCUMENT_ID.fullmatch(document_id):
            return self._deny(400, "invalid_request", principal.subject)
        row = self._conn.execute(
            "SELECT document_id, title, status FROM documents WHERE document_id = ? AND tenant_id = ?",
            (document_id, principal.tenant_id),
        ).fetchone()
        if row is None:
            return self._deny(404, "not_found", principal.subject)
        return {"status": 200, "body": {"document_id": row[0], "title": row[1], "status": row[2]}}
