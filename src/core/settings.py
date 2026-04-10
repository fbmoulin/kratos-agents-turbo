"""Centralised application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip()


def _get_int(name: str, default: int) -> int:
    value = _get_env(name)
    if value in (None, ""):
        return default
    return int(value)


def _get_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = _get_env(name)
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    service_name: str
    service_version: str
    environment: str
    log_level: str
    api_host: str
    api_port: int
    mcp_host: str
    mcp_port: int
    celery_broker_url: str
    celery_backend_url: str
    celery_task_queue: str
    celery_despacho_queue: str
    celery_decisao_queue: str
    default_agent_id: str
    default_task_message: str
    default_task_type: str
    allowed_task_types: tuple[str, ...]
    max_upload_bytes: int
    max_batch_files: int
    default_despacho_priority: int
    default_decisao_priority: int
    default_sentenca_priority: int
    local_storage_path: Path
    supabase_url: str | None
    supabase_key: str | None
    catalog_path: Path

    def health_payload(self) -> dict[str, str]:
        return {
            "status": "ok",
            "service": self.service_name,
            "version": self.service_version,
        }

    def queue_for_task_type(self, task_type: str) -> str:
        if task_type == "despacho":
            return self.celery_despacho_queue
        if task_type == "decisao":
            return self.celery_decisao_queue
        return self.celery_task_queue

    def default_priority_for_task_type(self, task_type: str) -> int:
        if task_type == "despacho":
            return self.default_despacho_priority
        if task_type == "decisao":
            return self.default_decisao_priority
        return self.default_sentenca_priority


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parents[2]
    return Settings(
        service_name=_get_env("SERVICE_NAME", "kratos-agents-turbo") or "kratos-agents-turbo",
        service_version=_get_env("SERVICE_VERSION", "0.3.0") or "0.3.0",
        environment=_get_env("APP_ENV", "development") or "development",
        log_level=(_get_env("LOG_LEVEL", "INFO") or "INFO").upper(),
        api_host=_get_env("API_HOST", "0.0.0.0") or "0.0.0.0",
        api_port=_get_int("API_PORT", 8000),
        mcp_host=_get_env("MCP_HOST", "0.0.0.0") or "0.0.0.0",
        mcp_port=_get_int("MCP_PORT", 8001),
        celery_broker_url=_get_env("CELERY_BROKER_URL", "redis://redis:6379/0")
        or "redis://redis:6379/0",
        celery_backend_url=_get_env("CELERY_BACKEND_URL", "redis://redis:6379/1")
        or "redis://redis:6379/1",
        celery_task_queue=_get_env("CELERY_TASK_QUEUE", "legal-tasks") or "legal-tasks",
        celery_despacho_queue=_get_env("CELERY_DESPACHO_QUEUE", "legal-despacho")
        or "legal-despacho",
        celery_decisao_queue=_get_env("CELERY_DECISAO_QUEUE", "legal-decisao")
        or "legal-decisao",
        default_agent_id=_get_env("DEFAULT_AGENT_ID", "legal-document-agent")
        or "legal-document-agent",
        default_task_message=_get_env(
            "DEFAULT_TASK_MESSAGE",
            "Gere uma minuta simples, objetiva e juridicamente revisável.",
        )
        or "Gere uma minuta simples, objetiva e juridicamente revisável.",
        default_task_type=_get_env("DEFAULT_TASK_TYPE", "despacho") or "despacho",
        allowed_task_types=_get_list(
            "ALLOWED_TASK_TYPES",
            ("despacho", "decisao", "sentenca"),
        ),
        max_upload_bytes=_get_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
        max_batch_files=_get_int("MAX_BATCH_FILES", 100),
        default_despacho_priority=_get_int("DEFAULT_DESPACHO_PRIORITY", 9),
        default_decisao_priority=_get_int("DEFAULT_DECISAO_PRIORITY", 6),
        default_sentenca_priority=_get_int("DEFAULT_SENTENCA_PRIORITY", 4),
        local_storage_path=Path(
            _get_env(
                "LOCAL_STORAGE_PATH",
                str(base_dir / "runtime" / "uploads"),
            )
            or (base_dir / "runtime" / "uploads")
        ),
        supabase_url=_get_env("SUPABASE_URL"),
        supabase_key=_get_env("SUPABASE_KEY"),
        catalog_path=base_dir / "src" / "agent" / "catalog" / "agents.yaml",
    )
