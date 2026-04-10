# AGENTS.md

## Repo Intent

This repository is the platform-core backend for a legal agent execution system.

Work should preserve these architectural constraints:

- event-first execution
- explicit task and session lifecycle
- append-only execution events
- declarative agent registry
- service-layer orchestration instead of transport-layer business logic

## Working Rules

- Treat `POST /tasks` as create-only unless a future change explicitly introduces a public resume/rebind contract.
- Keep `TaskService` authoritative for task lifecycle operations.
- Keep `SessionService` authoritative for session lifecycle operations.
- Avoid writing task status transitions directly through `db.update_task(...)` outside `TaskService`.
- Avoid placing heavy domain logic in the API layer.
- Keep orchestrator logic focused on coordination, not legal reasoning details.
- Maintain structured logging with `task_id` and `session_id` where operationally relevant.

## Catalog and Agent Rules

- Agent definitions live in `src/agent/catalog/agents.yaml`.
- Registry loading must fail fast on invalid catalog structure.
- New catalog fields should be introduced conservatively and validated explicitly.
- Do not add `projects.yaml` unless there is a concrete runtime consumer.

## Runtime and Persistence Rules

- Keep Redis as queue transport and Supabase/Postgres as persistence of record.
- Keep schema/code alignment between `src/db.py` and `infra/sql/schema.sql`.
- Prefer incremental service-layer changes over ad hoc logic in worker or API handlers.
- Do not introduce schema changes unless they are justified by a concrete runtime need.

## Validation Expectations

Before closing meaningful changes, run:

```bash
python -m compileall src tests
pytest -q
docker compose config
python -c "import pathlib, sys; sys.path.insert(0, str(pathlib.Path('.').resolve())); import src.api.main, src.worker.tasks, src.mcp.server; print('imports-ok')"
```

## Near-Term Priorities

- strengthen runtime reliability
- improve observability and audit views
- expand tests around lifecycle and persistence behavior
- prepare safe growth toward richer legal processing pipelines
