"""Task 01 candidate `reference`: idempotent order creation (controlled lab fixture)."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from collections.abc import Callable
from typing import Any

ALLOWED_CURRENCIES = frozenset({"EUR", "USD", "GBP"})
BODY_FIELDS = frozenset({"customer_ref", "currency", "items", "client_note"})
ITEM_FIELDS = frozenset({"sku", "quantity", "unit_price_minor"})
KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,64}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_ref TEXT NOT NULL,
    currency TEXT NOT NULL,
    total_minor INTEGER NOT NULL,
    items_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    request_fingerprint TEXT NOT NULL,
    order_id TEXT NOT NULL REFERENCES orders(order_id)
);
"""


class InvalidRequest(Exception):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _str_len_between(value: Any, low: int, high: int) -> bool:
    return isinstance(value, str) and low <= len(value) <= high


def normalize_body(body: Any) -> dict[str, Any]:
    """Validate the body and return the material fields in canonical form."""
    if not isinstance(body, dict) or not set(body) <= BODY_FIELDS:
        raise InvalidRequest("body")
    if not _str_len_between(body.get("customer_ref"), 1, 40):
        raise InvalidRequest("customer_ref")
    currency = body.get("currency")
    if not isinstance(currency, str) or currency.upper() not in ALLOWED_CURRENCIES:
        raise InvalidRequest("currency")
    if "client_note" in body and not _str_len_between(body["client_note"], 0, 200):
        raise InvalidRequest("client_note")
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise InvalidRequest("items")
    normalized = []
    for item in items:
        if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
            raise InvalidRequest("items")
        sku, quantity, price = item["sku"], item["quantity"], item["unit_price_minor"]
        if not _str_len_between(sku, 1, 32):
            raise InvalidRequest("items.sku")
        if not _is_int(quantity) or not 1 <= quantity <= 100:
            raise InvalidRequest("items.quantity")
        if not _is_int(price) or not 1 <= price <= 1_000_000:
            raise InvalidRequest("items.unit_price_minor")
        normalized.append({"sku": sku, "quantity": quantity, "unit_price_minor": price})
    if len({item["sku"] for item in normalized}) != len(normalized):
        raise InvalidRequest("items.sku")
    normalized.sort(key=lambda item: item["sku"])
    return {
        "customer_ref": body["customer_ref"],
        "currency": currency.upper(),
        "items": normalized,
    }


def fingerprint(normalized: dict[str, Any]) -> str:
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _error(status: int, error: str, field: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": error}
    if field is not None:
        body["field"] = field
    return {"status": status, "body": body}


def _order(status: int, order_id: str, currency: str, total: int) -> dict[str, Any]:
    return {
        "status": status,
        "body": {
            "order_id": order_id,
            "currency": currency,
            "total_minor": total,
            "idempotent_replay": status == 200,
        },
    }


class OrderService:
    def __init__(self, db_path: str) -> None:
        # Autocommit mode: transactions are explicit so BEGIN IMMEDIATE takes the write lock
        # before the idempotency lookup. The timeout makes concurrent callers wait for it.
        self._conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def create_order(
        self, request: dict[str, Any], before_commit: Callable[[], None] | None = None
    ) -> dict[str, Any]:
        if not isinstance(request, dict):
            return _error(422, "invalid_request", "request")
        key = request.get("idempotency_key")
        if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
            return _error(422, "invalid_request", "idempotency_key")
        try:
            normalized = normalize_body(request.get("body"))
        except InvalidRequest as exc:
            return _error(422, "invalid_request", exc.field)

        self._conn.execute("BEGIN IMMEDIATE")
        try:
            response = self._create_or_replay(key, normalized, before_commit)
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._conn.execute("COMMIT")
        return response

    def _create_or_replay(
        self,
        key: str,
        normalized: dict[str, Any],
        before_commit: Callable[[], None] | None,
    ) -> dict[str, Any]:
        request_fp = fingerprint(normalized)
        existing = self._conn.execute(
            "SELECT k.request_fingerprint, o.order_id, o.currency, o.total_minor "
            "FROM idempotency_keys k JOIN orders o ON o.order_id = k.order_id "
            "WHERE k.idempotency_key = ?",
            (key,),
        ).fetchone()
        if existing is not None:
            stored_fp, order_id, currency, total = existing
            if stored_fp != request_fp:
                return _error(409, "idempotency_key_reused_with_different_payload")
            return _order(200, order_id, currency, total)

        total = sum(item["quantity"] * item["unit_price_minor"] for item in normalized["items"])
        order_id = "ord_" + secrets.token_hex(8)
        self._conn.execute(
            "INSERT INTO orders (order_id, customer_ref, currency, total_minor, items_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                order_id,
                normalized["customer_ref"],
                normalized["currency"],
                total,
                json.dumps(normalized["items"], sort_keys=True),
            ),
        )
        self._conn.execute(
            "INSERT INTO idempotency_keys (idempotency_key, request_fingerprint, order_id) VALUES (?, ?, ?)",
            (key, request_fp, order_id),
        )
        if before_commit is not None:
            before_commit()
        return _order(201, order_id, normalized["currency"], total)
