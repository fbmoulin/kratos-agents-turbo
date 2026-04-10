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


def _get_bool(name: str, default: bool) -> bool:
    value = _get_env(name)
    if value in (None, ""):
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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
    celery_default_worker_concurrency: int
    celery_despacho_worker_concurrency: int
    celery_decisao_worker_concurrency: int
    celery_worker_prefetch_multiplier: int
    celery_visibility_timeout: int
    celery_retry_backoff_base_seconds: int
    celery_retry_backoff_max_seconds: int
    celery_despacho_max_retries: int
    celery_decisao_max_retries: int
    celery_sentenca_max_retries: int
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
    database_url: str | None
    database_min_pool_size: int
    database_max_pool_size: int
    supabase_url: str | None
    supabase_key: str | None
    operational_pending_dispatch_after_minutes: int
    operational_stuck_task_after_minutes: int
    otel_enabled: bool
    otel_service_namespace: str
    otel_exporter_otlp_endpoint: str | None
    otel_exporter_otlp_headers: str | None
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

    def max_retries_for_task_type(self, task_type: str) -> int:
        if task_type == "despacho":
            return self.celery_despacho_max_retries
        if task_type == "decisao":
            return self.celery_decisao_max_retries
        return self.celery_sentenca_max_retries


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
        celery_decisao_queue=_get_env("CELERY_DECISAO_QUEUE", "legal-decisao") or "legal-decisao",
        celery_default_worker_concurrency=_get_int("CELERY_DEFAULT_WORKER_CONCURRENCY", 1),
        celery_despacho_worker_concurrency=_get_int("CELERY_DESPACHO_WORKER_CONCURRENCY", 4),
        celery_decisao_worker_concurrency=_get_int("CELERY_DECISAO_WORKER_CONCURRENCY", 2),
        celery_worker_prefetch_multiplier=_get_int("CELERY_WORKER_PREFETCH_MULTIPLIER", 1),
        celery_visibility_timeout=_get_int("CELERY_VISIBILITY_TIMEOUT", 7200),
        celery_retry_backoff_base_seconds=_get_int("CELERY_RETRY_BACKOFF_BASE_SECONDS", 30),
        celery_retry_backoff_max_seconds=_get_int("CELERY_RETRY_BACKOFF_MAX_SECONDS", 600),
        celery_despacho_max_retries=_get_int("CELERY_DESPACHO_MAX_RETRIES", 3),
        celery_decisao_max_retries=_get_int("CELERY_DECISAO_MAX_RETRIES", 2),
        celery_sentenca_max_retries=_get_int("CELERY_SENTENCA_MAX_RETRIES", 1),
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
        database_url=_get_env("DATABASE_URL") or _get_env("SUPABASE_DB_URL"),
        database_min_pool_size=_get_int("DATABASE_MIN_POOL_SIZE", 1),
        database_max_pool_size=_get_int("DATABASE_MAX_POOL_SIZE", 5),
        supabase_url=_get_env("SUPABASE_URL"),
        supabase_key=_get_env("SUPABASE_KEY"),
        operational_pending_dispatch_after_minutes=_get_int(
            "OPS_PENDING_DISPATCH_AFTER_MINUTES",
            5,
        ),
        operational_stuck_task_after_minutes=_get_int("OPS_STUCK_TASK_AFTER_MINUTES", 30),
        otel_enabled=_get_bool("OTEL_ENABLED", False),
        otel_service_namespace=_get_env("OTEL_SERVICE_NAMESPACE", "kratos") or "kratos",
        otel_exporter_otlp_endpoint=_get_env("OTEL_EXPORTER_OTLP_ENDPOINT"),
        otel_exporter_otlp_headers=_get_env("OTEL_EXPORTER_OTLP_HEADERS"),
        catalog_path=base_dir / "src" / "agent" / "catalog" / "agents.yaml",
    )
