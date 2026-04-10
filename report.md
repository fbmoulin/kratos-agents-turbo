# Kratos Agents Turbo — Roadmap and TODOs

This document tracks the engineering backlog after the Phase 2 consolidation pass and the start of the batch-processing MVP.

## Current Baseline

The repository currently includes:

- declarative agent registry and YAML catalog
- task and session lifecycle services
- append-only event storage
- API support for task submission, inspection, cancellation, and event listing
- API support for batch submission, inspection, and batch cancellation
- Celery-based runtime with Redis
- staged local input handoff between API and worker
- direct PostgreSQL persistence against Supabase-hosted Postgres
- minimal automated test suite

## Phase Status

### Phase 1 — Foundation

Status: complete

Delivered:

- centralized settings
- FastAPI base
- worker runtime
- schema bootstrap
- event-first architecture skeleton

### Phase 2 — Consolidation

Status: complete

Delivered:

- `TaskService` as authoritative task lifecycle layer
- create-only public task submission
- task/session operational pairing
- `GET /tasks/{task_id}/events`
- registry hardening and fail-fast validation
- expanded tests for API, task lifecycle, and catalog validation

### Phase 3 — Batch MVP

Status: in progress

Delivered in the current slice:

- `batches` persistence model
- direct PostgreSQL persistence with connection pooling
- batch submission endpoint and aggregate batch inspection
- basic batch idempotency with SQL-backed reuse
- queue routing by `task_type`
- specific agent profiles for `despacho` and `decisao`
- local staging to avoid sending full PDFs through Redis
- initial SQL migrations under `infra/sql/migrations`

Immediate MVP target:

- sustain `50` `despacho` items per batch
- sustain `20` `decisao` items per batch
- keep RAG and embeddings out of scope for this slice

### Phase 4 — Next Hardening Targets

Status: planned

Priority backlog:

1. controlled retry semantics on top of the current idempotency baseline
2. stronger persistence failure handling and recovery semantics
3. object storage for large document payloads in production
4. richer operational audit views and event filtering
5. broader task/session integration tests against real persistence
6. metrics/tracing beyond basic structured logs

## TODOs

### Runtime and Reliability

- add integration validation for real Supabase Postgres-backed task/session/event writes
- replace local staging with production-grade object storage when deployment hardening starts
- review retry policy and failure semantics for batch items
- review per-queue worker concurrency for despacho vs decisao

### Observability

- add filtered event views by event type or step
- add batch-level event or audit projection if operator needs outgrow derived summaries
- add task duration and queue latency visibility
- define minimal operational metrics for success/failure/cancelled counts

### Catalog and Agents

- maintain separate profiles for `despacho` and `decisao`
- validate catalog schema more formally if complexity increases
- define conventions for `execution_mode`, capabilities, and tool metadata

### Documentation

- keep `README.md` aligned with public batch API and lifecycle behavior
- update `AGENTS.md` whenever repo-specific working rules change
- introduce an explicit changelog if delivery cadence increases

## Out of Scope for the Current Roadmap Slice

- public resume/rebind
- dashboard UI
- websocket streaming
- full authentication/authorization
- multi-agent orchestration
- RAG/vector database integration
- embeddings
- external court connectors

## Validation Baseline

The expected validation baseline for ongoing changes is:

```bash
python -m compileall src tests
pytest -q
docker compose config
python -c "import pathlib, sys; sys.path.insert(0, str(pathlib.Path('.').resolve())); import src.api.main, src.worker.tasks, src.mcp.server; print('imports-ok')"
```

Any future phase should preserve this baseline and extend it rather than replace it.
