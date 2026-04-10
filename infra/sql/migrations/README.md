# SQL Migrations

This directory contains ordered SQL migrations for Supabase-hosted PostgreSQL.

Current baseline:

1. `001_platform_core.sql`
2. `002_batch_idempotency.sql`
3. `003_task_dispatch_outbox.sql`
4. `004_phase2_operational_hardening.sql`
5. `005_dispatch_claims_and_session_uniqueness.sql`
6. `006_repo_migration_ledger.sql`

Recommended application order:

1. run `python scripts/apply_repo_migrations.py`
2. verify with `python scripts/verify_repo_migrations.py`
3. use `schema.sql` only as the latest consolidated snapshot for inspection and bootstrap reference

Rules:

- append new migrations; do not rewrite applied files
- keep `schema.sql` aligned with the latest cumulative state
- prefer additive, idempotent SQL where possible
- treat `internal.platform_migrations` as the repo-owned authoritative rollout ledger
- treat `supabase_migrations.schema_migrations` as auxiliary platform metadata; it may be partial for this project
