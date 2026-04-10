# Kratos Agents Turbo

![Status](https://img.shields.io/badge/status-phase_2_consolidated-0f172a?style=for-the-badge)
![Architecture](https://img.shields.io/badge/architecture-event--first-1d4ed8?style=for-the-badge)
![Domain](https://img.shields.io/badge/domain-legal_agents-0f766e?style=for-the-badge)
![Runtime](https://img.shields.io/badge/runtime-FastAPI%20%7C%20Celery%20%7C%20Redis-7c3aed?style=for-the-badge)
![Persistence](https://img.shields.io/badge/persistence-Supabase%20%7C%20Postgres-f59e0b?style=for-the-badge)

## 1. Current Position

`Kratos Agents Turbo` is the platform-core backend for a legal agent execution system.

The repository is no longer a queue-backed bootstrap. It now includes:

- declarative agent registry
- centralized settings and state machines
- service layer for task/session coordination
- append-only event log
- HTTP API, worker runtime, and MCP-like skill server
- SQL schema for tasks, sessions, and task logs
- minimal automated validation suite

This document is the primary operator/developer overview for the current implementation.

## 2. Product Direction

The project is intended to be the execution core of a future legal agent platform, with emphasis on:

- asynchronous legal document processing
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
| `Persistence Layer` | `tasks`, `sessions`, `task_logs` in Postgres |

Core design principles:

- `event-first execution`
- `task/session pairing`
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
6. serializes content to Celery
7. dispatches the worker job

### 5.2 Worker path

1. worker receives `task_id` and serialized content
2. `orchestrator_service` resolves the target agent
3. creates a new session
4. marks task and session as `running`
5. appends `TASK_STARTED`
6. executes agent steps and emits `TOOL_CALLED` / `STEP_EXECUTED`
7. finalizes task and session as `completed` or `failed`

### 5.3 Operational observability path

`GET /tasks/{task_id}/events`

1. validates that the task exists
2. loads the ordered event stream from `task_logs`
3. returns `task_id`, `count`, and ordered `events`

## 6. Public API

| Endpoint | Responsibility |
| --- | --- |
| `GET /health` | minimal liveness metadata |
| `POST /tasks` | submit a legal execution task |
| `GET /tasks` | list tasks |
| `GET /tasks/{task_id}` | read task state/result |
| `GET /tasks/{task_id}/events` | read ordered execution events |
| `POST /tasks/{task_id}/cancel` | cancel task and revoke Celery execution |

Important public contract:

- `POST /tasks` is create-only
- public resume/rebind is not exposed
- PDF is the only supported document input in the current phase

## 7. Data Model

Persistence is implemented on Supabase/PostgreSQL.

### `tasks`

Stores:

- request metadata
- requested and resolved agent identity
- task status
- result and error
- lifecycle timestamps

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

## 8. Agent Catalog

Current catalog:

- [`src/agent/catalog/agents.yaml`](./src/agent/catalog/agents.yaml)

Current base agent:

- `legal-document-agent`

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
- Supabase project with schema access

### 9.2 Configuration

1. Copy `.env.example` to `.env`
2. Set `SUPABASE_URL`
3. Set `SUPABASE_KEY`
4. Apply [`infra/sql/schema.sql`](./infra/sql/schema.sql)

### 9.3 Boot

```bash
docker compose up --build
```

Exposed services:

- API: `http://localhost:8000`
- MCP-like server: `http://localhost:8001`
- Redis: `localhost:6379`

### 9.4 Validation

```bash
python -m compileall src tests
pytest -q
docker compose config
python -c "import pathlib, sys; sys.path.insert(0, str(pathlib.Path('.').resolve())); import src.api.main, src.worker.tasks, src.mcp.server; print('imports-ok')"
```

Current automated coverage includes:

- create-only validation for `POST /tasks`
- session ownership safety
- task lifecycle state transitions
- task event endpoint envelope
- registry catalog failure cases

## 10. Operational Notes

- payloads are currently serialized through Celery as base64 content
- logs include `task_id` and `session_id` correlation fields
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
- ordered task event inspection endpoint
- initial automated test suite

### Next

- formal database migrations
- stronger task/session sync guarantees across persistence failures
- move large payloads out of the broker path
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
- court integrations

## 12. Summary

This repository should be understood as:

> a consolidated platform-core backend for a legal agent execution system

It is ready for continued hardening and controlled expansion, but it is not yet the final production platform.
