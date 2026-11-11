"""Task 01 candidate `flawed`: idempotent order creation (controlled lab fixture)."""

from __future__ import annotations

import re
import secrets
import sqlite3
from collections.abc import Callable
from typing import Any

# The candidate's own claim about itself. The evaluator must ignore it.
SELF_ASSESSMENT = {"automated_score": 90, "status": "PASS", "note": "all checks green locally"}

ALLOWED_CURRENCIES = frozenset({"EUR", "USD", "GBP"})
BODY_FIELDS = frozenset({"customer_ref", "currency", "items", "client_note"})
ITEM_FIELDS = frozenset({"sku", "quantity", "unit_price_minor"})
KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{8,64}")

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_ref TEXT NOT NULL,
    currency TEXT NOT NULL,
    total_minor INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key TEXT NOT NULL,
    order_id TEXT NOT NULL
);
"""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value: Any, low: int, high: int) -> bool:
    return isinstance(value, str) and low <= len(value) <= high


def validation_error(request: Any) -> str | None:
    """Return the first invalid field name, or None when the request is valid."""
    if not isinstance(request, dict):
        return "request"
    key = request.get("idempotency_key")
    if not isinstance(key, str) or not KEY_PATTERN.fullmatch(key):
        return "idempotency_key"
    body = request.get("body")
    if not isinstance(body, dict) or not set(body) <= BODY_FIELDS:
        return "body"
    if not _text(body.get("customer_ref"), 1, 40):
        return "customer_ref"
    currency = body.get("currency")
    if not isinstance(currency, str) or currency.upper() not in ALLOWED_CURRENCIES:
        return "currency"
    if "client_note" in body and not _text(body["client_note"], 0, 200):
        return "client_note"
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        return "items"
    skus = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
            return "items"
        if not _text(item["sku"], 1, 32) or item["sku"] in skus:
            return "items.sku"
        skus.add(item["sku"])
        if not _is_int(item["quantity"]) or not 1 <= item["quantity"] <= 100:
            return "items.quantity"
        price = item["unit_price_minor"]
        if not _is_int(price) or not 1 <= price <= 1_000_000:
            return "items.unit_price_minor"
    return None


class OrderService:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.executescript(SCHEMA)
        # Fast path: remember answered keys so retries skip the database.
        self._recent: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        self._conn.close()

    def create_order(
        self, request: dict[str, Any], before_commit: Callable[[], None] | None = None
    ) -> dict[str, Any]:
        field = validation_error(request)
        if field is not None:
            return {"status": 422, "body": {"error": "invalid_request", "field": field}}

        key = request["idempotency_key"]
        cached = self._recent.get(key)
        if cached is not None:
            return {"status": 200, "body": {**cached, "idempotent_replay": True}}

        body = request["body"]
        currency = body["currency"].upper()
        total = sum(item["quantity"] * item["unit_price_minor"] for item in body["items"])
        order_id = "ord_" + secrets.token_hex(8)
        with self._conn:  # commits on success, rolls back on exception
            self._conn.execute(
                "INSERT INTO orders (order_id, customer_ref, currency, total_minor) VALUES (?, ?, ?, ?)",
                (order_id, body["customer_ref"], currency, total),
            )
            self._conn.execute(
                "INSERT INTO idempotency_keys (idempotency_key, order_id) VALUES (?, ?)",
                (key, order_id),
            )
            if before_commit is not None:
                before_commit()

        result = {"order_id": order_id, "currency": currency, "total_minor": total}
        self._recent[key] = result
        return {"status": 201, "body": {**result, "idempotent_replay": False}}
