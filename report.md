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

### Phase 2 — Operational Closeout

Status: complete

Delivered:

- `TaskService` as authoritative task lifecycle layer
- create-only public task submission
- task/session operational pairing
- `GET /tasks/{task_id}/events`
- registry hardening and fail-fast validation
- expanded tests for API, task lifecycle, and catalog validation
- dedicated Celery workers per queue profile
- bounded retry policy with explicit retry classification
- Prometheus metrics endpoint and operational summary endpoint
- optional OpenTelemetry bootstrap for API/worker/Postgres/Redis
- local Prometheus, Grafana, and Flower operator stack
- GitHub Actions CI for lint, tests, compose validation, import smoke, and Docker build

### Phase 3 — Batch MVP

Status: next

Delivered in the current slice:

- `batches` persistence model
- direct PostgreSQL persistence with connection pooling
- validated direct runtime persistence against a real Supabase project using the Session Pooler path
- batch submission endpoint and aggregate batch inspection
- basic batch idempotency with SQL-backed reuse
- queue routing by `task_type`
- specific agent profiles for `despacho` and `decisao`
- local staging to avoid sending full PDFs through Redis
- initial SQL migrations under `infra/sql/migrations`
- task dispatch outbox and reconcile path for broker recovery
- runtime fixes for UUID-safe dispatch and JSON payload serialization

Immediate MVP target:

- sustain `50` `despacho` items per batch
- sustain `20` `decisao` items per batch
- keep RAG and embeddings out of scope for this slice
- use `scripts/validate_batch_capacity.py` as the baseline harness for repeatable capacity validation

Latest validated local baseline:

- `despacho=50` -> completed in `36.549s`, throughput `1.368 docs/s`, task p95 `3.086s`
- `decisao=20` -> completed in `43.108s`, throughput `0.464 docs/s`, task p95 `6.904s`

This benchmark was executed against the compose stack with the current dedicated workers and Supabase-backed persistence.

### Phase 4 — Next Hardening Targets

Status: planned

Priority backlog:

1. throughput validation for `50` `despacho` and `20` `decisao`
2. object storage for large document payloads in production
3. richer operational audit views and event filtering
4. broader task/session integration tests against real persistence
5. PDF ingestion/extraction pipeline
6. spreadsheet-driven batch-candidate analysis skill/agent

## TODOs

### Runtime and Reliability

- add integration validation for real Supabase Postgres-backed task/session/event writes
- replace local staging with production-grade object storage when deployment hardening starts
- benchmark per-queue worker concurrency for despacho vs decisao
- collect and compare repeated results from `scripts/validate_batch_capacity.py`
- validate reconcile and retry behavior under broker outage scenarios

### Observability

- add filtered event views by event type or step
- add batch-level event or audit projection if operator needs outgrow derived summaries
- add dashboards and alert rules on top of Prometheus/Grafana
- validate OTLP export path in a real collector-backed environment

### Catalog and Agents

- maintain separate profiles for `despacho` and `decisao`
- validate catalog schema more formally if complexity increases
- define conventions for `execution_mode`, capabilities, and tool metadata

### Documentation

- keep `README.md` aligned with public batch API and lifecycle behavior
- keep `.env.example` aligned with the current Supabase connection model and compose host ports
- update `AGENTS.md` whenever repo-specific working rules change
- keep local runbooks aligned with retry/reconcile/metrics behavior

## Out of Scope for the Current Roadmap Slice

- public resume/rebind
- dashboard UI
- websocket streaming
- full authentication/authorization
- LGPD/anonymization
- multi-agent orchestration
- RAG/vector database integration
- embeddings
- external court connectors

## Validation Baseline

The expected validation baseline for ongoing changes is:

```bash
python -m ruff check src tests scripts .github
python -m compileall src tests scripts
pytest -q
docker compose config
python -c "import pathlib, sys; sys.path.insert(0, str(pathlib.Path('.').resolve())); import src.api.main, src.worker.tasks, src.mcp.server; print('imports-ok')"
docker build . -t kratos-agents-turbo-local
```

Any future phase should preserve this baseline and extend it rather than replace it.
