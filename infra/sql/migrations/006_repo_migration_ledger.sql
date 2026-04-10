create schema if not exists internal;

create table if not exists internal.platform_migrations (
    version text primary key check (version ~ '^[0-9]{3}$'),
    filename text not null unique,
    checksum_sha256 text not null,
    source text not null default 'repo',
    applied_at timestamptz not null default now()
);

insert into internal.platform_migrations (
    version,
    filename,
    checksum_sha256,
    source
)
values
    ('001', '001_platform_core.sql', '35a56102186e4fcdc8088d0290328c68e2173daed649651e8c8e4db09c84174b', 'legacy-backfill'),
    ('002', '002_batch_idempotency.sql', '8d4b81108ebc7db6a2797487669480d7cde566d4ff3b96461abe5b5376eb7d28', 'legacy-backfill'),
    ('003', '003_task_dispatch_outbox.sql', '0332b89d2f5c3ed6dc2d05a8011d59e5196b8941cb5711fc48083095bb8cdb93', 'legacy-backfill'),
    ('004', '004_phase2_operational_hardening.sql', 'ac6499426fa488cb14497bd94a67570c8893c9d8e8fbf083a7a24ffdadc50093', 'legacy-backfill'),
    ('005', '005_dispatch_claims_and_session_uniqueness.sql', '22ce60df3fda48b572573ab344a8dd1e7250b70821849b8a515fbfd059fa03cc', 'legacy-backfill')
on conflict (version) do update
set
    filename = excluded.filename,
    checksum_sha256 = excluded.checksum_sha256,
    source = excluded.source;
