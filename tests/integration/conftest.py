from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from src import db
from src.core.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = (ROOT / "infra" / "sql" / "schema.sql").read_text(encoding="utf-8")
TRUNCATE_SQL = (
    "truncate table task_logs, task_dispatches, sessions, tasks, batches "
    "restart identity cascade"
)


def _reset_runtime_state() -> None:
    get_settings.cache_clear()
    if db._pool is not None:
        db._pool.close()
        db._pool = None


def _connect() -> psycopg.Connection:
    database_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured for integration tests")
    return psycopg.connect(database_url, autocommit=True)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv("RUN_INTEGRATION_TESTS") == "1":
        return
    skip_marker = pytest.mark.skip(reason="integration tests require RUN_INTEGRATION_TESTS=1")
    for item in items:
        if "tests/integration" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip_marker)


@pytest.fixture(scope="session", autouse=True)
def integration_database() -> None:
    _reset_runtime_state()
    with _connect() as conn:
        conn.execute(SCHEMA_SQL)
    yield
    _reset_runtime_state()


@pytest.fixture(autouse=True)
def clean_database(integration_database: None) -> None:
    with _connect() as conn:
        conn.execute(TRUNCATE_SQL)
    _reset_runtime_state()
    yield
    with _connect() as conn:
        conn.execute(TRUNCATE_SQL)
    _reset_runtime_state()
