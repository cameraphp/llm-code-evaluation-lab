# Task specifications

There are three original programming tasks. Each full contract (interface, request and response
formats, semantics and an oracle summary) lives in its own file:

| Task | Contract | Interface | Candidate risk it probes |
|---|---|---|---|
| `task-01` | [examples/task-01-api-idempotency/TASK.md](examples/task-01-api-idempotency/TASK.md) | `OrderService(db_path)` | Duplicate orders, replaying a changed payload, races, restart loss, partial commits |
| `task-02` | [examples/task-02-tenant-authorization/TASK.md](examples/task-02-tenant-authorization/TASK.md) | `DocumentService(db_path, identity, audit)` | BOLA/IDOR, collection scope, spoofed tenant or role, missing function-level checks, leaky denials |
| `task-03` | [examples/task-03-agent-jobs/TASK.md](examples/task-03-agent-jobs/TASK.md) | `JobWorker(db_path, effects, clock)` | Weak tool allowlists, re-execution on redelivery, unbounded or misclassified retries, stored secrets |

## Shared conventions

- **API-style, not deployed.** Handlers return `{"status": int, "body": dict}`. There is no HTTP
  server.
- **Fictional data only.** Orders, tenants, users, documents and job targets are invented.
  Amounts are integer minor units.
- **Persistence.** SQLite files in a per-check temporary directory. The oracle reads stored state
  through an independent read-only connection, so assertions cover actual state, not only statuses.
- **Determinism.** Barriers with bounded joins (task-01), a fake clock (task-03), no sleeps and no
  real time in reports.
- **Candidates.** Each task has three registered fixtures: `reference`, `flawed` and `partial`.
  Seeded defects are documented in `fixtures/<task>/DEFECTS.md`, outside the candidate-facing
  contract. The evaluator never reads them.

## What counts as ground truth

Ground truth is the **current written contract, its oracle assertions and the controlled
reference fixture**. A passing reference shows that the contract and the checks are consistent with
each other. It does not prove that every correct implementation would pass: a reasonable design
the contract does not anticipate (for example answering "in progress" to concurrent duplicates in
task-01) would fail. Blind spots shared by the reference and the tests are a known limitation. There is no hidden or
held-out test suite, and no claim of generalization beyond these fixtures.
