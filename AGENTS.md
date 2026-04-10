# AGENTS.md

## Repo Intent

This repository is the platform-core backend for a legal agent execution system.

Work should preserve these architectural constraints:

- event-first execution
- batch-oriented MVP for despacho and decisao
- explicit task and session lifecycle
- append-only execution events
- declarative agent registry
- service-layer orchestration instead of transport-layer business logic

## Working Rules

- Treat `POST /tasks` as create-only unless a future change explicitly introduces a public resume/rebind contract.
- Treat `POST /batches` as create-only; do not add resume/rebind semantics to batch submission in this phase.
- Keep `TaskService` authoritative for task lifecycle operations.
- Keep `SessionService` authoritative for session lifecycle operations.
- Avoid writing task status transitions directly through `db.update_task(...)` outside `TaskService`.
- Avoid placing heavy domain logic in the API layer.
- Keep orchestrator logic focused on coordination, not legal reasoning details.
- Maintain structured logging with `task_id` and `session_id` where operationally relevant.
- Prefer queue selection by `task_type` instead of a single undifferentiated worker flow.
- Keep `/metrics` and `/operations/summary` aligned with real runtime behavior; do not expose ad hoc operational data directly from handlers.

## Catalog and Agent Rules

- Agent definitions live in `src/agent/catalog/agents.yaml`.
- Registry loading must fail fast on invalid catalog structure.
- New catalog fields should be introduced conservatively and validated explicitly.
- Do not add `projects.yaml` unless there is a concrete runtime consumer.
- Preserve dedicated profiles for `despacho` and `decisao` unless a better routing contract is introduced.

## Runtime and Persistence Rules

- Keep Redis as queue transport and Supabase-hosted PostgreSQL as persistence of record.
- Prefer direct PostgreSQL access via `DATABASE_URL` or `SUPABASE_DB_URL` over the Supabase REST client for runtime persistence paths.
- For local and IPv4-bound environments, prefer the Supabase `Session Pooler` connection string in `DATABASE_URL`.
- Keep broker payloads small; prefer staged file references over raw document bytes in Celery arguments.
- Keep database-to-broker handoff recoverable through the task dispatch outbox; do not return to direct fire-and-forget enqueue from the API.
- Keep queue isolation for `despacho`, `decisao`, and fallback work; do not collapse them into one worker path without a clear throughput reason.
- Keep retry behavior explicit and bounded per `task_type`; do not add infinite retries or silent broker redelivery loops.
- Keep schema/code alignment between `src/db.py` and `infra/sql/schema.sql`.
- Keep ordered SQL migrations in `infra/sql/migrations/` and treat `schema.sql` as the latest snapshot.
- Prefer incremental service-layer changes over ad hoc logic in worker or API handlers.
- Do not introduce schema changes unless they are justified by a concrete runtime need.
- Keep the API and worker aligned on the shared staging path configured by `LOCAL_STORAGE_PATH`.
- Keep `REDIS_HOST_PORT` and `GRAFANA_HOST_PORT` configurable in local compose flows so this repo can coexist with other local stacks.
- Treat Prometheus/Grafana as the main metrics path and Flower only as an auxiliary operator console.
- Keep OpenTelemetry optional and environment-driven; instrumentation must not block the core batch path when disabled.

## Validation Expectations

Before closing meaningful changes, run:

```bash
python -m ruff check src tests scripts .github
python -m compileall src tests scripts
pytest -q
docker compose config
python -c "import pathlib, sys; sys.path.insert(0, str(pathlib.Path('.').resolve())); import src.api.main, src.worker.tasks, src.mcp.server; print('imports-ok')"
docker build . -t kratos-agents-turbo-local
```

## Near-Term Priorities

- stabilize batch throughput for `despacho` and `decisao`
- improve observability and audit views for batches
- expand tests around batch lifecycle and persistence behavior
- prepare safe growth toward production storage and retry semantics
