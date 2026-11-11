# Task 01: API-style idempotent order creation

Version `task-01/v1`. This describes **API-style behaviour** modelled as a Python handler. It is
not a deployed HTTP endpoint. All data is fictional.

## Interface

Implement a module that exposes:

```python
class OrderService:
    def __init__(self, db_path: str) -> None: ...   # opens its OWN sqlite3 connection, creates schema if absent
    def create_order(self, request: dict, before_commit: Callable[[], None] | None = None) -> dict: ...
    def close(self) -> None: ...
```

A service instance is created and used on one thread. Independent instances on the same
`db_path` stand in for independent handlers or processes.

### Minimum observable schema (the oracle reads it through a separate read-only connection)

```sql
orders(order_id TEXT PRIMARY KEY, customer_ref TEXT NOT NULL, currency TEXT NOT NULL, total_minor INTEGER NOT NULL, ...)
idempotency_keys(idempotency_key ..., ...)   -- one row per accepted key
```

## Request

```json
{"idempotency_key": "order-key-0001",
 "body": {"customer_ref": "cust-1001", "currency": "EUR",
          "items": [{"sku": "SKU-RED-MUG", "quantity": 2, "unit_price_minor": 1250}],
          "client_note": "optional"}}
```

Validation (any violation → 422, no write):

- `idempotency_key`: string matching `^[A-Za-z0-9_-]{8,64}$`.
- `body` is an object. The allowed fields are exactly `customer_ref`, `currency`, `items` and
  optional `client_note`. Unknown fields are rejected.
- `customer_ref`: string, 1–40 chars. `currency`: `EUR`, `USD` or `GBP`, case-insensitive.
  `client_note`: string of at most 200 chars.
- `items`: 1–20 objects, each with exactly `sku` (string, 1–32 chars, unique within the order),
  `quantity` (integer 1–100) and `unit_price_minor` (integer 1–1,000,000, minor units).
  Booleans and floats are not integers.

## Normalized payload (request fingerprint)

The fingerprint covers these **material** fields: `customer_ref`; `currency` upper-cased; and
`items` sorted by `sku`, each with `sku`, `quantity` and `unit_price_minor`. Excluded: JSON key order,
item order, currency case and `client_note`. `total_minor = Σ quantity × unit_price_minor`
(integer arithmetic only).

## Responses (`{"status": int, "body": dict}`)

| Situation | Status | Body |
|---|---|---|
| New key, valid payload | 201 | `order_id` (non-empty string), `currency`, `total_minor`, `idempotent_replay: false` |
| Known key, same normalized payload | 200 | the **original** `order_id`, `currency`, `total_minor`, `idempotent_replay: true` |
| Known key, different normalized payload | 409 | `error`, and **no** `order_id` |
| Invalid key or payload | 422 | `error`, `field` |

Concurrency: a request that arrives while another request with the same key is in flight
must wait for it, then answer as a replay (200) or conflict (409). Answering
"in progress" is not accepted in v1.

## Fault-injection hook and recovery

On the path that **creates** an order, call `before_commit()` exactly once, after all writes
for the order and its key record and before the single commit that makes them durable. If it raises,
roll back fully and either re-raise the exception or return status 503. Afterwards the
same key must be usable. Do not call the hook on replay, conflict or validation paths.

## Evaluation oracle (evaluator-side summary)

Each check runs in a fresh temporary directory with a new SQLite file. Assertions read
stored state through an independent read-only connection, not only response statuses.

| Check | Setup → assertion |
|---|---|
| T1-C01 | one request → 201; stored rows: 1 order (`cust-1001`, `EUR`, 3097) and 1 key; stored `order_id` = response `order_id` |
| T1-C02 | same request twice and then a new key → 201, 200 (same id), 201 (different id); 2 orders and 2 keys |
| T1-C03 | equivalent payload (reordered items, `eur`, extra `client_note`) → 200 with the same id; 1 order |
| T1-C04 | 14 invalid requests → 422 each; 0 orders and 0 keys; then a valid request with the same key → 201 |
| T1-S01 | 5 material variants (customer, currency, quantity, unit price, added item) → 409 with no `order_id`; original replay still 200; stored order unchanged |
| T1-S02 | 3 rounds: schema initialised, 2 threads each with its own service and `Barrier(2)`, joins bounded to 15 s → per round statuses {200, 201}, same id, 1 order, 1 key |
| T1-R01 | first response discarded after commit (1 order verified) → retry 200 with the stored id; 1 order |
| T1-R02 | create, close the service, replay with a new service on the same file → 200 with the same id; 1 order |
| T1-R03 | `before_commit` raises → hook called once, failure surfaced (exception or 503), 0 orders and 0 keys; retry → 201 and 1 order |

Fixture sizes: 2 base items (3 × 199 + 2 × 1250 = 3097 minor units), at most 3 items in any request,
2 racing workers. No sleeps are used for synchronisation.
