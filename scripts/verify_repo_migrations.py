from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-only",
        action="store_true",
        help="Validate repo migration files without connecting to a database.",
    )
    args = parser.parse_args()

    _load_dotenv()
    from src.core import get_settings
    from src.core.migration_governance import (
        discover_repo_migrations,
        verify_repo_migrations,
    )

    migrations = discover_repo_migrations(REPO_ROOT / "infra" / "sql" / "migrations")
    if args.repo_only:
        print(
            json.dumps(
                {
                    "repo_count": len(migrations),
                    "repo_versions": [migration.version for migration in migrations],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL or SUPABASE_DB_URL must be configured")

    with psycopg.connect(
        settings.database_url,
        row_factory=dict_row,
        autocommit=True,
    ) as conn:
        report = verify_repo_migrations(conn, migrations)

    print(json.dumps(report, indent=2, sort_keys=True))
    if (
        report["missing_versions"]
        or report["checksum_mismatches"]
        or report["unexpected_versions"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
