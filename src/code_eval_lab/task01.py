"""Task 01 oracle: API-style idempotent order creation (contract `task-01/v1`).

Evaluator-side only. Expected values, check logic and the scoring manifest live here and are
never taken from candidate fixtures. See examples/task-01-api-idempotency/TASK.md.
"""

from __future__ import annotations

import contextlib
import copy
import sqlite3
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from code_eval_lab.scoring import CandidateViolation, CheckSpec, Recorder

TASK_ID = "task-01"
TITLE = "API-style idempotent order creation"
VERSION = "task-01/v1"

KEY = "order-key-0001"
OTHER_KEY = "order-key-0002"
RACE_ROUNDS = 3
BARRIER_TIMEOUT_S = 10.0
JOIN_TIMEOUT_S = 15.0
EXPECTED_TOTAL = 3 * 199 + 2 * 1250  # 3097 minor units
EXPECTED_STORED = ["cust-1001", "EUR", EXPECTED_TOTAL]


def base_body() -> dict[str, Any]:
    return {
        "customer_ref": "cust-1001",
        "currency": "EUR",
        "items": [
            {"sku": "SKU-BLUE-PEN", "quantity": 3, "unit_price_minor": 199},
            {"sku": "SKU-RED-MUG", "quantity": 2, "unit_price_minor": 1250},
        ],
    }


def make_request(body: dict[str, Any] | None = None, key: Any = KEY) -> dict[str, Any]:
    return {"idempotency_key": key, "body": base_body() if body is None else body}


class InjectedFault(Exception):
    """Raised by the oracle's before_commit hook to simulate a crash before commit."""


class HarnessError(Exception):
    """The oracle could not establish candidate behaviour; the check becomes ERROR."""


# --- candidate interaction ---------------------------------------------------------------


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

    @property
    def order_id(self) -> str | None:
        value = self.body.get("order_id")
        return value if isinstance(value, str) and value else None


def same_order(a: Outcome, b: Outcome) -> bool:
    return a.order_id is not None and a.order_id == b.order_id


def call(service: Any, request: dict[str, Any], before_commit: Callable[[], None] | None = None) -> Outcome:
    """Invoke the candidate with a private copy; its exceptions are behaviour, not harness errors."""
    try:
        response = service.create_order(copy.deepcopy(request), before_commit=before_commit)
    except Exception as exc:
        return Outcome(None, {}, type(exc).__name__)
    if not isinstance(response, dict):
        return Outcome(None, {}, None)
    status = response.get("status")
    body = response.get("body")
    return Outcome(
        status if isinstance(status, int) and not isinstance(status, bool) else None,
        copy.deepcopy(body) if isinstance(body, dict) else {},
        None,
    )


@contextlib.contextmanager
def open_service(module: ModuleType, db_path: Path) -> Iterator[Any]:
    try:
        service = module.OrderService(str(db_path))
    except Exception as exc:
        raise CandidateViolation(
            "construct", "OrderService(db_path) constructs without raising", f"raised {type(exc).__name__}"
        ) from exc
    try:
        yield service
    finally:
        with contextlib.suppress(Exception):  # close() behaviour is not part of task-01/v1
            service.close()


@dataclass(frozen=True)
class StoreState:
    orders: list[tuple[Any, ...]]  # (order_id, customer_ref, currency, total_minor)
    key_rows: int

    def stored_fields(self) -> list[Any] | None:
        return list(self.orders[0][1:]) if len(self.orders) == 1 else None

    def stored_id(self) -> Any:
        return self.orders[0][0] if len(self.orders) == 1 else None


def read_state(db_path: Path) -> StoreState:
    """Inspect committed state through an independent read-only connection."""
    if not db_path.is_file():
        raise HarnessError("store file was not created; stored state cannot be verified")
    conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True, timeout=5.0)
    try:
        orders = conn.execute(
            "SELECT order_id, customer_ref, currency, total_minor FROM orders ORDER BY order_id"
        ).fetchall()
        key_rows = conn.execute("SELECT COUNT(*) FROM idempotency_keys").fetchone()[0]
    finally:
        conn.close()
    return StoreState(orders, key_rows)


def expect_single_stored(rec: Recorder, state: StoreState, response: Outcome | None = None) -> None:
    rec.expect("stored_orders", "exactly one order row is stored", 1, len(state.orders))
    rec.expect(
        "stored_fields",
        "stored [customer_ref, currency, total_minor] match the original request",
        EXPECTED_STORED,
        state.stored_fields(),
    )
    rec.expect("stored_key_records", "exactly one idempotency record is stored", 1, state.key_rows)
    if response is not None:
        rec.expect(
            "stored_identity",
            "stored order_id equals the response order_id",
            True,
            response.order_id is not None and state.stored_id() == response.order_id,
        )


# --- checks ------------------------------------------------------------------------------


def check_create(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db = workdir / "orders.db"
    with open_service(module, db) as service:
        created = call(service, make_request())
    rec.expect("status", "a valid new request returns 201", 201, created.observed)
    rec.expect(
        "order_id_present", "response carries a non-empty string order_id", True, created.order_id is not None
    )
    rec.expect(
        "response_total",
        "response total_minor = sum(quantity * unit_price_minor)",
        EXPECTED_TOTAL,
        created.body.get("total_minor"),
    )
    expect_single_stored(rec, read_state(db), created)


def check_replay(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db = workdir / "orders.db"
    with open_service(module, db) as service:
        first = call(service, make_request())
        replay = call(service, make_request())
        other = call(service, make_request(key=OTHER_KEY))
    rec.expect("first_status", "first request returns 201", 201, first.observed)
    rec.expect("replay_status", "same key and payload returns 200", 200, replay.observed)
    rec.expect("replay_identity", "replay returns the original order_id", True, same_order(first, replay))
    rec.expect(
        "replay_total", "replay returns the original total", EXPECTED_TOTAL, replay.body.get("total_minor")
    )
    rec.expect("new_key_status", "a different key with the same payload returns 201", 201, other.observed)
    rec.expect(
        "new_key_distinct",
        "the different key yields a distinct order_id",
        True,
        other.order_id is not None and other.order_id != first.order_id,
    )
    state = read_state(db)
    rec.expect("stored_orders", "two orders are stored (one per key)", 2, len(state.orders))
    rec.expect("stored_key_records", "two idempotency records are stored", 2, state.key_rows)


def check_normalized_equivalent(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    equivalent = {
        "items": [
            {"unit_price_minor": 1250, "quantity": 2, "sku": "SKU-RED-MUG"},
            {"unit_price_minor": 199, "quantity": 3, "sku": "SKU-BLUE-PEN"},
        ],
        "client_note": "leave at reception",
        "currency": "eur",
        "customer_ref": "cust-1001",
    }
    db = workdir / "orders.db"
    with open_service(module, db) as service:
        first = call(service, make_request())
        again = call(service, make_request(equivalent))
    rec.expect("first_status", "first request returns 201", 201, first.observed)
    rec.expect(
        "equivalent_status",
        "reordered items, lower-case currency and client_note are not material: 200",
        200,
        again.observed,
    )
    rec.expect(
        "equivalent_identity",
        "equivalent request returns the original order_id",
        True,
        same_order(first, again),
    )
    expect_single_stored(rec, read_state(db), first)


def _invalid_requests() -> list[tuple[str, dict[str, Any]]]:
    def body_with(**changes: Any) -> dict[str, Any]:
        body = base_body()
        body.update(changes)
        return make_request(body)

    def first_item_with(**changes: Any) -> dict[str, Any]:
        body = base_body()
        body["items"][0].update(changes)
        return make_request(body)

    no_customer = base_body()
    del no_customer["customer_ref"]
    item = base_body()["items"][0]
    return [
        ("missing_key", {"body": base_body()}),
        ("short_key", make_request(key="k-1")),
        ("key_bad_chars", make_request(key="order key 0001!")),
        ("key_not_string", make_request(key=12345678)),
        ("missing_body", {"idempotency_key": KEY}),
        ("missing_customer_ref", make_request(no_customer)),
        ("unsupported_currency", body_with(currency="JPY")),
        ("unknown_body_field", body_with(discount_minor=100)),
        ("empty_items", body_with(items=[])),
        ("duplicate_sku", body_with(items=[item, dict(item)])),
        ("zero_quantity", first_item_with(quantity=0)),
        ("bool_quantity", first_item_with(quantity=True)),
        ("float_unit_price", first_item_with(unit_price_minor=12.5)),
        ("negative_unit_price", first_item_with(unit_price_minor=-1)),
    ]


def check_validation_no_write(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db = workdir / "orders.db"
    with open_service(module, db) as service:
        rejected = [(name, call(service, request)) for name, request in _invalid_requests()]
        after_rejections = read_state(db)
        valid = call(service, make_request())
    for name, outcome in rejected:
        rec.expect(f"case_{name}", f"invalid request '{name}' returns 422", 422, outcome.observed)
    rec.expect("no_orders_written", "no order rows after invalid requests", 0, len(after_rejections.orders))
    rec.expect(
        "no_keys_written", "no idempotency records after invalid requests", 0, after_rejections.key_rows
    )
    rec.expect(
        "key_still_usable", "the key used by rejected requests can still create (201)", 201, valid.observed
    )
    rec.expect(
        "stored_orders_after_valid",
        "exactly one order after the valid request",
        1,
        len(read_state(db).orders),
    )


def _material_variants() -> list[tuple[str, dict[str, Any]]]:
    variants = []
    for name, mutate in (
        ("customer_ref", lambda b: b.update(customer_ref="cust-2002")),
        ("currency", lambda b: b.update(currency="USD")),
        ("quantity", lambda b: b["items"][1].update(quantity=5)),
        ("unit_price_minor", lambda b: b["items"][0].update(unit_price_minor=299)),
        (
            "item_added",
            lambda b: b["items"].append({"sku": "SKU-GREEN-CUP", "quantity": 1, "unit_price_minor": 800}),
        ),
    ):
        body = base_body()
        mutate(body)
        variants.append((name, body))
    return variants


def check_conflict_on_changed_payload(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db = workdir / "orders.db"
    with open_service(module, db) as service:
        first = call(service, make_request())
        variants = [(name, call(service, make_request(body))) for name, body in _material_variants()]
        replay = call(service, make_request())
    rec.expect("first_status", "first request returns 201", 201, first.observed)
    for name, outcome in variants:
        rec.expect(
            f"variant_{name}_status", f"same key with changed {name} returns 409", 409, outcome.observed
        )
        rec.expect(
            f"variant_{name}_no_order",
            f"conflict for changed {name} does not return an order_id",
            False,
            outcome.order_id is not None,
        )
    rec.expect("original_replay_status", "original payload still replays with 200", 200, replay.observed)
    rec.expect(
        "original_replay_identity",
        "original replay returns the original order_id",
        True,
        same_order(first, replay),
    )
    expect_single_stored(rec, read_state(db), first)


def _race_once(module: ModuleType, db: Path) -> list[Outcome]:
    barrier = threading.Barrier(2, timeout=BARRIER_TIMEOUT_S)
    outcomes: list[Outcome | None] = [None, None]
    failures: list[BaseException | None] = [None, None]

    def worker(index: int) -> None:
        try:
            with open_service(module, db) as service:  # independent handler + connection
                barrier.wait()
                outcomes[index] = call(service, make_request())
        except BaseException as exc:  # surfaced on the main thread below
            failures[index] = exc
            barrier.abort()

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(JOIN_TIMEOUT_S)
    if any(thread.is_alive() for thread in threads):
        raise HarnessError("race worker exceeded the bounded join; outcome not established")
    for exc in failures:
        if isinstance(exc, CandidateViolation):
            raise exc
    for exc in failures:
        if exc is not None:
            raise HarnessError(f"race worker failed: {type(exc).__name__}") from exc
    if any(outcome is None for outcome in outcomes):
        raise HarnessError("race worker produced no outcome")
    return [outcome for outcome in outcomes if outcome is not None]


def check_concurrent_same_key(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    statuses, consistent, stored, keys, identity = [], [], [], [], []
    for round_no in range(RACE_ROUNDS):
        db = workdir / f"race-{round_no}.db"
        with open_service(module, db):
            pass  # precondition: schema initialised before the race
        first, second = _race_once(module, db)
        state = read_state(db)
        statuses.append(sorted((first.observed, second.observed), key=str))
        consistent.append(same_order(first, second))
        stored.append(len(state.orders))
        keys.append(state.key_rows)
        identity.append(first.order_id is not None and state.stored_id() == first.order_id)
    rec.expect("statuses", "each round answers one 201 and one 200", [[200, 201]] * RACE_ROUNDS, statuses)
    rec.expect(
        "same_order_id",
        "each round: both responses carry the same order_id",
        [True] * RACE_ROUNDS,
        consistent,
    )
    rec.expect("stored_orders", "each round: exactly one order stored", [1] * RACE_ROUNDS, stored)
    rec.expect("stored_key_records", "each round: exactly one idempotency record", [1] * RACE_ROUNDS, keys)
    rec.expect(
        "stored_identity",
        "each round: stored order_id equals the response order_id",
        [True] * RACE_ROUNDS,
        identity,
    )


def check_response_loss(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db = workdir / "orders.db"
    with open_service(module, db) as service:
        call(service, make_request())  # committed, but the response is lost in transit
        committed = read_state(db)
        retry = call(service, make_request())
    rec.expect(
        "committed_before_loss", "the lost attempt committed exactly one order", 1, len(committed.orders)
    )
    rec.expect("retry_status", "retry after a lost response returns 200", 200, retry.observed)
    rec.expect(
        "retry_identity",
        "retry returns the order_id that was actually stored",
        True,
        retry.order_id is not None and retry.order_id == committed.stored_id(),
    )
    expect_single_stored(rec, read_state(db), retry)


def check_restart_replay(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    db = workdir / "orders.db"
    with open_service(module, db) as service:
        first = call(service, make_request())
    with open_service(module, db) as restarted:  # new handler instance and connection
        replay = call(restarted, make_request())
    rec.expect("first_status", "first request returns 201", 201, first.observed)
    rec.expect("replay_status", "replay after restart returns 200", 200, replay.observed)
    rec.expect(
        "replay_identity",
        "replay after restart returns the original order_id",
        True,
        same_order(first, replay),
    )
    expect_single_stored(rec, read_state(db), first)


def check_failure_before_commit(module: ModuleType, workdir: Path, rec: Recorder) -> None:
    hook_calls: list[str] = []

    def crash_before_commit() -> None:
        hook_calls.append("before_commit")
        raise InjectedFault("simulated crash before commit")

    db = workdir / "orders.db"
    with open_service(module, db) as service:
        failed = call(service, make_request(), before_commit=crash_before_commit)
        after_failure = read_state(db)
        retry = call(service, make_request())
    rec.expect(
        "hook_invoked", "before_commit is called exactly once on the creating path", 1, len(hook_calls)
    )
    rec.record(
        "failure_surfaced",
        "the pre-commit failure surfaces as InjectedFault or status 503",
        "raised InjectedFault | 503",
        failed.observed,
        failed.raised == "InjectedFault" or failed.status == 503,
    )
    rec.expect("no_order_after_failure", "no order is stored after the failure", 0, len(after_failure.orders))
    rec.expect("no_key_after_failure", "no idempotency record after the failure", 0, after_failure.key_rows)
    rec.expect("retry_status", "retry with the same key creates the order (201)", 201, retry.observed)
    expect_single_stored(rec, read_state(db), retry)


# --- manifest ----------------------------------------------------------------------------
# Positional fields: id, title, category, weight, severity, taxonomy, suspected_cause, remediation.
# fmt: off
MANIFEST: tuple[CheckSpec, ...] = (
    CheckSpec(
        "T1-C01", "New request creates exactly one order with a stable identity",
        "correctness", 10, "major", "logic_correctness",
        "Creation path does not persist the order and key record in the documented schema, "
        "or the response diverges from stored state.",
        "Insert the order and its key record in one transaction and build the response "
        "from the stored values.",
    ),
    CheckSpec(
        "T1-C02", "Same key and payload replays the original; a new key creates a new order",
        "correctness", 10, "major", "data_integrity_idempotency",
        "Replay lookup is missing or keyed by payload instead of idempotency key.",
        "Look up the key record before creating; return the stored order with status 200.",
    ),
    CheckSpec(
        "T1-C03", "Normalized-equivalent payload is treated as the same request",
        "correctness", 8, "major", "logic_correctness",
        "Fingerprint is computed over raw input instead of the normalized payload.",
        "Fingerprint the canonical normalized payload defined in TASK.md (items sorted by "
        "sku, upper-case currency, client_note excluded).",
    ),
    CheckSpec(
        "T1-C04", "Invalid key or payload is rejected with 422 and writes nothing",
        "correctness", 12, "critical", "data_integrity_idempotency",
        "Validation is incomplete or runs after a write, or rejected requests reserve the key.",
        "Validate key and payload fully before opening the write transaction; return 422 "
        "without touching the store.",
    ),
    CheckSpec(
        "T1-S01", "Same key with a materially changed payload returns 409 conflict",
        "safety_integrity", 15, "critical", "data_integrity_idempotency",
        "The request fingerprint is not compared on replay, or it omits material fields.",
        "Store a fingerprint over every material normalized field with the key; return 409 "
        "without order data when a replay's fingerprint differs.",
    ),
    CheckSpec(
        "T1-S02", "Concurrent same-key requests store one order with consistent responses",
        "safety_integrity", 15, "critical", "data_integrity_idempotency",
        "Idempotency is not enforced by durable state inside a serialized write transaction "
        "(for example a process-local cache or check-then-insert without a unique key).",
        "Put a UNIQUE/PRIMARY KEY on the idempotency key and take the write lock "
        "(BEGIN IMMEDIATE) before the lookup.",
    ),
    CheckSpec(
        "T1-R01", "Retry after a committed-but-lost response returns the stored order",
        "resilience", 5, "major", "data_integrity_idempotency",
        "The retry path does not consult durable state committed by the earlier attempt.",
        "Resolve every request through the stored key record, not through in-flight memory.",
    ),
    CheckSpec(
        "T1-R02", "Replay survives a handler and connection restart",
        "resilience", 8, "critical", "data_integrity_idempotency",
        "Idempotency state is held in memory and lost when the handler or connection restarts.",
        "Persist the key record in the same SQLite transaction as the order and read it on "
        "every request.",
    ),
    CheckSpec(
        "T1-R03", "Failure before commit leaves no order and the key stays retryable",
        "resilience", 7, "critical", "data_integrity_idempotency",
        "Order and key are committed in separate transactions, the hook is not wired at the "
        "commit boundary, or rollback is missing on error.",
        "Call before_commit inside the single transaction just before COMMIT and roll back "
        "on any exception before re-raising or returning 503.",
    ),
)
# fmt: on

CHECKS: dict[str, Callable[[ModuleType, Path, Recorder], None]] = {
    "T1-C01": check_create,
    "T1-C02": check_replay,
    "T1-C03": check_normalized_equivalent,
    "T1-C04": check_validation_no_write,
    "T1-S01": check_conflict_on_changed_payload,
    "T1-S02": check_concurrent_same_key,
    "T1-R01": check_response_loss,
    "T1-R02": check_restart_replay,
    "T1-R03": check_failure_before_commit,
}
