# SQL Migrations

This directory contains ordered SQL migrations for Supabase-hosted PostgreSQL.

Current baseline:

1. `001_platform_core.sql`
2. `002_batch_idempotency.sql`
3. `003_task_dispatch_outbox.sql`

Recommended application order:

1. apply each migration file in lexical order inside the Supabase SQL editor or through your deployment pipeline
2. use `schema.sql` only as the latest consolidated snapshot for inspection and bootstrap reference

Rules:

- append new migrations; do not rewrite applied files
- keep `schema.sql` aligned with the latest cumulative state
- prefer additive, idempotent SQL where possible
