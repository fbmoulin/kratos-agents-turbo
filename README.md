# Kratos Agents Turbo

![Status](https://img.shields.io/badge/status-phase_3_batch_mvp-0f172a?style=for-the-badge)
![Architecture](https://img.shields.io/badge/architecture-event--first-1d4ed8?style=for-the-badge)
![Domain](https://img.shields.io/badge/domain-legal_agents-0f766e?style=for-the-badge)
![Runtime](https://img.shields.io/badge/runtime-FastAPI%20%7C%20Celery%20%7C%20Redis-7c3aed?style=for-the-badge)
![Persistence](https://img.shields.io/badge/persistence-Supabase%20%7C%20Postgres-f59e0b?style=for-the-badge)
![MVP Focus](https://img.shields.io/badge/mvp-batch_despacho_%2B_decisao-7c2d12?style=for-the-badge)

## 1. Current Position

`Kratos Agents Turbo` is the platform-core backend for a legal agent execution system.

The repository is no longer a queue-backed bootstrap. It now includes:

- declarative agent registry
- centralized settings and state machines
- service layer for task/session coordination
- append-only event log
- HTTP API, worker runtime, and MCP-like skill server
- direct PostgreSQL persistence against Supabase-hosted Postgres
- SQL schema and versioned migrations
- minimal automated validation suite

The current MVP focus is operational batch throughput for judicial drafts:

- at least `50` documents of `despacho`
- at least `20` documents of `decisao`
- no RAG or embeddings in this phase

This document is the primary operator/developer overview for the current implementation.

## 2. Product Direction

The project is intended to be the execution core of a future legal agent platform, with emphasis on:

- asynchronous legal document processing
- batch submission for despacho and decisao
- execution traceability and auditability
- explicit task and session lifecycle
- declarative growth of agents and capabilities
- safe backend evolution toward more critical workloads

## 3. Architectural Model

The backend is organized into six layers:

| Layer | Responsibility |
| --- | --- |
| `Agent Layer` | declarative agent identity, prompt, skills, tools, capabilities |
| `Runtime Layer` | Celery queueing and worker execution |
| `Session Layer` | session creation, progress, transitions, lifecycle |
| `Event Layer` | append-only operational events |
| `Service Layer` | orchestration, task lifecycle, validation, routing |
| `Persistence Layer` | `batches`, `tasks`, `sessions`, `task_logs` in Postgres |

Core design principles:

- `event-first execution`
- `task/session pairing`
- `batch-first operational visibility for the MVP`
- `explicit transitions`
- `create-only public task submission`
- `declarative agent growth`

## 4. Repository Layout

| Path | Purpose |
| --- | --- |
| `src/api/` | FastAPI transport layer |
| `src/agent/` | agent implementations, registry, YAML catalog |
| `src/core/` | settings, logging, exceptions, state machines |
| `src/events/` | event storage abstraction |
| `src/services/` | task, session, validator, router, orchestrator services |
| `src/session/` | session manager |
| `src/worker/` | Celery runtime |
| `src/mcp/` | MCP-like skill server |
| `src/skills/` | reusable legal processing skills |
| `infra/sql/` | SQL bootstrap artifacts |
| `tests/` | API/service/registry/state-machine tests |

## 5. Execution Flow

### 5.1 Public request path

`POST /tasks`

1. receives a PDF plus execution metadata
2. validates payload through `validator_service`
3. rejects `session_id`; the endpoint is create-only
4. creates a new task in `queued`
5. appends `TASK_CREATED`
6. stages content to a shared local path
7. dispatches the worker job

### 5.2 Public batch path

`POST /batches`

1. receives multiple PDFs with one `task_type` and one instruction message
2. validates cardinality against `MAX_BATCH_FILES`
3. optionally reuses an existing batch when `idempotency_key` matches
4. creates one `batch` record inside a SQL transaction
4. creates one `task` per file with `batch_id` and `batch_item_index`
5. appends one `TASK_CREATED` per task
6. stages each file to shared local storage
7. dispatches each task to the queue selected for its `task_type`

### 5.3 Worker path

1. worker receives `task_id` and staged file reference
2. `orchestrator_service` resolves the target agent
3. creates a new session
4. marks task and session as `running`
5. appends `TASK_STARTED`
6. executes agent steps and emits `TOOL_CALLED` / `STEP_EXECUTED`
7. finalizes task and session as `completed` or `failed`

### 5.4 Operational observability paths

`GET /tasks/{task_id}/events`

1. validates that the task exists
2. loads the ordered event stream from `task_logs`
3. returns `task_id`, `count`, and ordered `events`

`GET /batches/{batch_id}`

1. loads the batch record
2. loads all tasks for that batch
3. derives aggregate status from task counts
4. returns operator-friendly summary with per-task status

## 6. Public API

| Endpoint | Responsibility |
| --- | --- |
| `GET /health` | minimal liveness metadata |
| `POST /tasks` | submit a legal execution task |
| `POST /batches` | submit a batch of legal execution tasks |
| `GET /tasks` | list tasks |
| `GET /tasks/{task_id}` | read task state/result |
| `GET /tasks/{task_id}/events` | read ordered execution events |
| `POST /tasks/{task_id}/cancel` | cancel task and revoke Celery execution |
| `GET /batches` | list batch summaries |
| `GET /batches/{batch_id}` | read aggregate batch state |
| `POST /batches/{batch_id}/cancel` | cancel queued/running tasks in the batch |

Important public contract:

- `POST /tasks` is create-only
- `POST /batches` is create-only
- `POST /batches` accepts optional `idempotency_key`
- public resume/rebind is not exposed
- PDF is the only supported document input in the current phase
- all files in one batch share the same `task_type`

## 7. Data Model

Persistence is implemented on Supabase-hosted PostgreSQL through direct SQL connections.

### `tasks`

Stores:

- request metadata
- optional `batch_id`
- requested and resolved agent identity
- task status
- result and error
- lifecycle timestamps

### `batches`

Stores:

- submission-level metadata
- batch cardinality
- requested agent and requested priority
- optional `idempotency_key`
- aggregate status derivation inputs

### `sessions`

Stores:

- lifecycle status
- current step
- progress
- execution metadata

### `task_logs`

Stores:

- append-only event history
- event type, step, status, message
- structured payload for audit and replay

Schema:

- [`infra/sql/schema.sql`](./infra/sql/schema.sql)
- [`infra/sql/migrations/001_platform_core.sql`](./infra/sql/migrations/001_platform_core.sql)

## 8. Agent Catalog

Current catalog:

- [`src/agent/catalog/agents.yaml`](./src/agent/catalog/agents.yaml)

Current agent profiles:

- `legal-despacho-agent`
- `legal-decisao-agent`
- `legal-document-agent` for `sentenca` fallback

Current built-in skill chain:

1. `extract_text_from_pdf`
2. `classify_document`
3. `generate_decision`

The registry now fails early when the catalog is invalid, including:

- empty catalog
- duplicate agent ids
- unknown implementations
- malformed `supported_task_types`

## 9. Local Development

### 9.1 Prerequisites

- Docker
- Docker Compose
- Supabase project with PostgreSQL access

### 9.2 Configuration

1. Copy `.env.example` to `.env`
2. Set `DATABASE_URL` or `SUPABASE_DB_URL`
3. Apply migrations from [`infra/sql/migrations/`](./infra/sql/migrations/)
4. Keep [`infra/sql/schema.sql`](./infra/sql/schema.sql) as the consolidated snapshot

`SUPABASE_URL` and `SUPABASE_KEY` can remain available for future platform integrations, but persistence now depends on direct PostgreSQL connectivity.

### 9.3 Boot

```bash
docker compose up --build
```

Exposed services:

- API: `http://localhost:8000`
- MCP-like server: `http://localhost:8001`
- Redis: `localhost:6379`

The compose stack mounts `./runtime` into API and worker containers so staged inputs can be shared without sending full PDFs through Redis.

### 9.4 Validation

```bash
python -m compileall src tests
pytest -q
docker compose config
python -c "import pathlib, sys; sys.path.insert(0, str(pathlib.Path('.').resolve())); import src.api.main, src.worker.tasks, src.mcp.server; print('imports-ok')"
```

Current automated coverage includes:

- create-only validation for `POST /tasks`
- batch validation and batch submission envelope
- session ownership safety
- task lifecycle state transitions
- task event endpoint envelope
- router preference for more specific agent profiles
- registry catalog failure cases

## 10. Operational Notes

- uploaded documents are staged locally and the worker receives a file reference
- persistence uses direct PostgreSQL connections with pooling instead of the Supabase REST client
- batch creation is transactional and supports basic idempotent reuse via `idempotency_key`
- queues are split by task type for the MVP:
  - `despacho` -> `CELERY_DESPACHO_QUEUE`
  - `decisao` -> `CELERY_DECISAO_QUEUE`
  - fallback types -> `CELERY_TASK_QUEUE`
- logs include `task_id` and `session_id` correlation fields
- batch endpoints provide aggregate status derived from underlying task states
- `TaskService` is the authoritative lifecycle service for tasks
- `SessionService` remains authoritative for session lifecycle
- the implementation is production-shaped, not production-complete

## 11. Roadmap

### Completed

- platform settings and health endpoint
- declarative agent registry
- task/session/event persistence model
- service-layer orchestration
- create-only task submission
- create-only batch submission
- direct PostgreSQL persistence with connection pooling
- basic batch idempotency for repeated submissions
- ordered task event inspection endpoint
- queue routing by `task_type`
- local staging to reduce broker pressure
- initial automated test suite

### Next

- stronger batch retry policy beyond the current idempotency baseline
- stronger task/session sync guarantees across persistence failures
- object storage replacement for local staged inputs in production
- richer validator behavior for multiple agents and execution modes
- stronger event replayability and audit views
- operational metrics and tracing

### Explicitly Out of Scope for Now

- public resume/rebind
- frontend/dashboard implementation
- websocket streaming
- full authn/authz
- multi-agent orchestration
- RAG and vector storage
- embeddings and retrieval pipelines
- court integrations

## 12. Summary

This repository should be understood as:

> a consolidated platform-core backend for a legal agent execution system

It is ready for continued hardening toward a production batch-processing backend, but it is not yet the final production platform.
