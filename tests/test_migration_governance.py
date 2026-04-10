from __future__ import annotations

from pathlib import Path

import pytest
from src.core import ApplicationError
from src.core.migration_governance import (
    LEDGER_SCHEMA,
    LEDGER_TABLE,
    RepoMigration,
    discover_repo_migrations,
    ledger_bootstrap_sql,
    verify_repo_migrations,
)


def test_discover_repo_migrations_ignores_non_sql_and_sorts(tmp_path: Path):
    (tmp_path / "README.md").write_text("ignore", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("select 3;", encoding="utf-8")
    (tmp_path / "001_first.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "002_second.sql").write_text("select 2;", encoding="utf-8")

    migrations = discover_repo_migrations(tmp_path)

    assert [migration.version for migration in migrations] == [
        "001_first",
        "002_second",
        "003_third",
    ]
    assert [migration.filename for migration in migrations] == [
        "001_first.sql",
        "002_second.sql",
        "003_third.sql",
    ]
    assert all(migration.checksum for migration in migrations)


def test_discover_repo_migrations_requires_contiguous_prefixes(tmp_path: Path):
    (tmp_path / "001_first.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "003_third.sql").write_text("select 3;", encoding="utf-8")

    with pytest.raises(ApplicationError, match="expected 002 but found 003"):
        discover_repo_migrations(tmp_path)


def test_ledger_bootstrap_sql_targets_platform_meta_repo_migrations():
    sql = ledger_bootstrap_sql()

    assert f"create schema if not exists {LEDGER_SCHEMA}" in sql
    assert f"create table if not exists {LEDGER_SCHEMA}.{LEDGER_TABLE}" in sql
    assert "checksum" in sql
    assert "execution_source" in sql


def test_verify_repo_migrations_reports_missing_and_checksum_drift(monkeypatch):
    migrations = [
        RepoMigration(
            version="001_first",
            filename="001_first.sql",
            path=Path("001_first.sql"),
            checksum="abc",
            sql="select 1;",
        ),
        RepoMigration(
            version="002_second",
            filename="002_second.sql",
            path=Path("002_second.sql"),
            checksum="def",
            sql="select 2;",
        ),
    ]

    monkeypatch.setattr(
        "src.core.migration_governance.load_applied_repo_migrations",
        lambda conn: {
            "001_first": {"version": "001_first", "checksum": "changed"},
            "003_extra": {"version": "003_extra", "checksum": "ghi"},
        },
    )
    monkeypatch.setattr(
        "src.core.migration_governance.load_supabase_managed_migrations",
        lambda conn: [
            {
                "version": "20260410184932",
                "name": "dispatch_claims_and_session_uniqueness",
            }
        ],
    )

    report = verify_repo_migrations(object(), migrations)

    assert report["missing_versions"] == ["002_second"]
    assert report["checksum_mismatches"] == ["001_first"]
    assert report["unexpected_versions"] == ["003_extra"]
    assert report["managed_versions"] == ["20260410184932"]
