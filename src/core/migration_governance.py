"""Repo-owned SQL migration governance helpers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.core import ApplicationError

LEDGER_SCHEMA = "internal"
LEDGER_TABLE = "platform_migrations"


@dataclass(frozen=True)
class RepoMigration:
    version: str
    filename: str
    path: Path
    checksum_sha256: str
    sql: str


def discover_repo_migrations(migrations_dir: Path) -> list[RepoMigration]:
    migrations: list[RepoMigration] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if not path.name[:3].isdigit():
            continue
        sql_text = path.read_text(encoding="utf-8").strip()
        migrations.append(
            RepoMigration(
                version=path.stem,
                filename=path.name,
                path=path,
                checksum=sha256(sql_text.encode("utf-8")).hexdigest(),
                sql=sql_text,
            )
        )
    if not migrations:
        raise ApplicationError(f"No SQL migrations found in {migrations_dir}")
    validate_repo_migration_sequence(migrations)
    return migrations


def validate_repo_migration_sequence(migrations: list[RepoMigration]) -> None:
    seen_prefixes: set[str] = set()
    expected_numeric_version = 1
    for migration in migrations:
        numeric_prefix = migration.filename.split("_", 1)[0]
        if numeric_prefix in seen_prefixes:
            raise ApplicationError(f"Duplicate migration version prefix: {numeric_prefix}")
        seen_prefixes.add(numeric_prefix)
        if int(numeric_prefix) != expected_numeric_version:
            raise ApplicationError(
                "Repo migrations must be contiguous and ordered; "
                f"expected {expected_numeric_version:03d} but found {numeric_prefix}"
            )
        expected_numeric_version += 1


def ledger_bootstrap_sql() -> str:
    return f"""
    create schema if not exists {LEDGER_SCHEMA};

    create table if not exists {LEDGER_SCHEMA}.{LEDGER_TABLE} (
        version text primary key,
        filename text not null unique,
        checksum text not null,
        execution_source text not null default 'script',
        applied_at timestamptz not null default now()
    );
    """


def ensure_repo_migration_ledger(conn: Any) -> None:
    with conn.cursor() as cursor:
        cursor.execute(ledger_bootstrap_sql())


def load_applied_repo_migrations(conn: Any) -> dict[str, dict[str, Any]]:
    ensure_repo_migration_ledger(conn)
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            select version, filename, checksum, execution_source, applied_at
            from {LEDGER_SCHEMA}.{LEDGER_TABLE}
            order by version
            """
        )
        rows = cursor.fetchall() or []
    return {row["version"]: row for row in rows}


def load_supabase_managed_migrations(conn: Any) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            select exists (
                select 1
                from information_schema.tables
                where table_schema = 'supabase_migrations'
                  and table_name = 'schema_migrations'
            ) as present
            """
        )
        present = cursor.fetchone()
        if not present or not present["present"]:
            return []
        cursor.execute(
            """
            select version, name
            from supabase_migrations.schema_migrations
            order by version
            """
        )
        return list(cursor.fetchall() or [])


def apply_repo_migrations(
    conn: Any,
    migrations: list[RepoMigration],
    *,
    execution_source: str,
) -> dict[str, Any]:
    applied_versions: list[str] = []
    skipped_versions: list[str] = []
    existing = load_applied_repo_migrations(conn)

    for migration in migrations:
        applied = existing.get(migration.version)
        if applied is not None:
            if applied["checksum"] != migration.checksum:
                raise ApplicationError(
                    f"Checksum mismatch for already applied migration '{migration.version}'"
                )
            skipped_versions.append(migration.version)
            continue

        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(migration.sql)
                cursor.execute(
                    f"""
                    insert into {LEDGER_SCHEMA}.{LEDGER_TABLE} (
                        version,
                        filename,
                        checksum,
                        execution_source
                    )
                    values (%s, %s, %s, %s)
                    """,
                    (
                        migration.version,
                        migration.filename,
                        migration.checksum,
                        execution_source,
                    ),
                )
        applied_versions.append(migration.version)

    ledger_rows = load_applied_repo_migrations(conn)
    managed_rows = load_supabase_managed_migrations(conn)
    return {
        "applied": applied_versions,
        "skipped": skipped_versions,
        "ledger_count": len(ledger_rows),
        "managed_count": len(managed_rows),
        "managed_versions": [row["version"] for row in managed_rows],
    }


def verify_repo_migrations(conn: Any, migrations: list[RepoMigration]) -> dict[str, Any]:
    repo_by_version = {migration.version: migration for migration in migrations}
    applied = load_applied_repo_migrations(conn)
    missing = [migration.version for migration in migrations if migration.version not in applied]
    mismatched = [
        migration.version
        for migration in migrations
        if migration.version in applied
        and applied[migration.version]["checksum"] != migration.checksum
    ]
    unexpected = sorted(version for version in applied if version not in repo_by_version)
    managed = load_supabase_managed_migrations(conn)
    return {
        "repo_count": len(migrations),
        "ledger_count": len(applied),
        "missing_versions": missing,
        "checksum_mismatches": mismatched,
        "unexpected_versions": unexpected,
        "managed_count": len(managed),
        "managed_versions": [row["version"] for row in managed],
    }
