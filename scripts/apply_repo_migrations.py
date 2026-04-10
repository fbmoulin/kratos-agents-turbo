from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name and name not in os.environ:
            os.environ[name] = value


def main() -> int:
    _load_dotenv()
    from src.core import get_settings
    from src.core.migration_governance import apply_repo_migrations, discover_repo_migrations

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL or SUPABASE_DB_URL must be configured")

    migrations = discover_repo_migrations(REPO_ROOT / "infra" / "sql" / "migrations")

    with psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        autocommit=True,
    ) as conn:
        report = apply_repo_migrations(
            conn,
            migrations,
            execution_source="scripts/apply_repo_migrations.py",
        )

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
