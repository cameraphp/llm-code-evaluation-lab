# Task 02: Multi-tenant document authorization

Version `task-02/v1`. This is an API-style read service modelled as a Python handler, not a
running web server. The tenants, users and documents are fictional.

## Interface

```python
class DocumentService:
    def __init__(self, db_path: str, identity: Callable[[str], Principal | None],
                 audit: Callable[[dict], None]) -> None: ...
    def handle(self, request: dict) -> dict: ...      # returns {"status": int, "body": dict}
    def close(self) -> None: ...
```

- `db_path` points to an existing SQLite store that the harness seeds. The service only reads it:
  `documents(document_id, tenant_id, title, status, internal_notes, owner_contact)`.
- `identity(token)` is the **trusted server-side identity lookup**. It returns an immutable
  `Principal(subject, tenant_id, roles: frozenset[str])` or `None` for an unknown token. It may
  raise if the identity directory is unavailable.
- `audit(event)` is optional tracing. If it is used, each event is a dict whose keys are a
  subset of `operation`, `outcome`, `reason`, `subject`, `document_id`, with `str` or `None` values.
  Events must not contain tokens, titles, notes, contacts or tenant IDs.

## Request

```json
{"operation": "get_document" | "list_documents",
 "headers": {"Authorization": "Bearer <token>"},
 "params": {"document_id": "doc-n-001"}}
```

Any other header or param, such as `X-Tenant-Id`, `X-Roles` or `params.tenant_id`, is **ignored**.
Scope comes only from the principal returned by `identity`.

## Processing order and semantics

1. **Shape.** If `request` is not an object with string `operation`, object `headers` and object
   `params`, the response is **400** `{"error": "invalid_request"}`.
2. **Authentication** (who is calling). A missing header, a scheme other than `Bearer `, an empty
   token or an unknown token gives **401** `{"error": "unauthenticated"}`. If `identity` raises, the
   service fails closed with **503** `{"error": "identity_unavailable"}`.
3. **Operation.** An unknown operation gives **400** `{"error": "invalid_request"}`.
4. **Authorization, function level** (what the caller may do). Both operations need the role
   `documents:read`. Without it the response is **403** `{"error": "forbidden"}`, before any lookup.
5. **Input validation** (not authorization). `document_id` must match `^doc-[a-z0-9-]{1,40}$`.
   Otherwise the response is **400** `{"error": "invalid_request"}`. A well-formed ID grants nothing.
6. **Authorization, object level** (which rows). Every lookup is scoped by
   `principal.tenant_id`. Another tenant's document and a nonexistent document **deliberately
   share the same response**, **404** `{"error": "not_found"}`, so the response does not reveal
   whether the ID exists.

On success:

- `get_document` returns **200** with exactly `{"document_id", "title", "status"}`.
- `list_documents` returns **200** `{"items": [...]}`, containing only the caller's tenant rows,
  sorted by `document_id`, each with exactly those three fields.

`internal_notes`, `owner_contact` and `tenant_id` are never returned. Error bodies are exactly
`{"error": <code>}`.

## Evaluation oracle (evaluator-side summary)

Fixtures: 2 tenants (`tenant-north`, `tenant-south`) with 2 documents each. There are 3 tokens:
a north reader, a south reader and a north viewer without `documents:read`. Unknown tokens act as
unauthenticated callers. Leak scans look for sensitive *categories*: other-tenant ID, other-tenant
title, internal notes, owner contact and bearer token. Reports record category names, never the
sensitive values.

| Check | Assertion |
|---|---|
| T2-C01 | north reader gets `doc-n-001` → 200, exactly the public fields, values match the store, no sensitive categories |
| T2-C02 | each reader's list → only their own IDs, public fields only, no other-tenant categories |
| T2-C03 | 4 unauthenticated variants × 2 operations → 401 `{"error":"unauthenticated"}`, no data |
| T2-C04 | north viewer: get, list and get-nonexistent → 403 `{"error":"forbidden"}`, no data |
| T2-S01 | north reader gets a south document → 404 identical to the nonexistent response, no south data; and the reverse |
| T2-S02 | spoofed `X-Tenant-Id`, `X-Roles`, `X-User` and `params.tenant_id` change nothing (list scope, cross-tenant get, viewer get) |
| T2-S03 | every denial body is an exact error; denial bodies and audit events have no sensitive categories; audit keys are allowed |
| T2-R01 | 7 malformed requests (shape, operation, id type, length, quote or traversal characters) → 400, no data, no exception |
| T2-R02 | identity lookup raises → get and list fail closed with 503 and no data |
