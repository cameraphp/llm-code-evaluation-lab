# Seeded defects: Task 02 fixtures

These notes are for the fixture author. They are **not** candidate-facing, and the evaluator
**does not read them**. The fixtures are controlled lab implementations written with AI assistance and are pending owner review.
They are not outputs from an LLM experiment. Their digests are pinned in `src/code_eval_lab/registry.py`.

## `reference`

Authentication via the identity lookup; function-level role check before any data access;
format validation kept separate from authorization; tenant-scoped lookups; the shared 404;
a public-field projection; and minimal audit events.

## `flawed`

| Defect | Code location | Expected observable effect |
|---|---|---|
| F1 BOLA/IDOR: get looks up by `document_id` only | `handle`, get branch | A south document is readable by the north reader |
| F2 Over-exposure: `SELECT *` on get | `handle`, get branch | `internal_notes`, `owner_contact` and `tenant_id` are returned |
| F3 Collection scope from the client: list honours `params.tenant_id` and `X-Tenant-Id` | `handle`, list branch | A spoofed tenant lists another tenant's rows |
| F4 Unsafe tracing: denials audit the raw request | `_deny` | Bearer tokens appear in audit events |
| F5 Untrusted self-label `CANDIDATE_LABEL = "reference"` | module constant | Must have no effect |

## `partial`

It fixes F1–F4. One genuine violation remains:

| Defect | Code location | Expected observable effect |
|---|---|---|
| P1 Missing function-level authorization on list: the role check runs only on the get path | `handle` | A same-tenant caller without `documents:read` can list documents |
