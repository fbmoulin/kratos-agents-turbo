"""Persistence helpers backed by Supabase/PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client

from src.core import PersistenceError, get_settings

_client: Client | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_client() -> Client:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_key:
            raise PersistenceError(
                "SUPABASE_URL and SUPABASE_KEY must be configured before using persistence"
            )
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def create_task(
    *,
    task_id: str,
    file_name: str,
    task_type: str,
    status: str,
    message: str,
    priority: int = 0,
    requested_agent_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    execution_mode: str = "document",
    input_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "id": task_id,
        "session_id": session_id,
        "requested_agent_id": requested_agent_id,
        "agent_id": agent_id,
        "file_name": file_name,
        "task_type": task_type,
        "status": status,
        "message": message,
        "priority": priority,
        "execution_mode": execution_mode,
        "input_metadata": input_metadata or {},
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    result = _get_client().table("tasks").insert(payload).execute()
    return result.data[0] if result.data else payload


def update_task(task_id: str, **fields: Any) -> dict[str, Any]:
    update_data = {**fields, "updated_at": utc_now()}
    result = _get_client().table("tasks").update(update_data).eq("id", task_id).execute()
    data = result.data or []
    if not data:
        raise PersistenceError(f"Task '{task_id}' could not be updated")
    return data[0]


def get_task(task_id: str) -> dict[str, Any] | None:
    result = _get_client().table("tasks").select("*").eq("id", task_id).limit(1).execute()
    data = result.data or []
    return data[0] if data else None


def list_tasks(status: str | None = None) -> list[dict[str, Any]]:
    query = _get_client().table("tasks").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)
    result = query.execute()
    return list(result.data or [])


def create_session(
    *,
    session_id: str,
    task_id: str,
    agent_id: str,
    status: str,
    execution_mode: str = "document",
    metadata: dict[str, Any] | None = None,
    progress: int = 0,
    current_step: str | None = None,
) -> dict[str, Any]:
    payload = {
        "id": session_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "status": status,
        "execution_mode": execution_mode,
        "metadata": metadata or {},
        "progress": progress,
        "current_step": current_step,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    result = _get_client().table("sessions").insert(payload).execute()
    return result.data[0] if result.data else payload


def update_session(session_id: str, **fields: Any) -> dict[str, Any]:
    update_data = {**fields, "updated_at": utc_now()}
    result = _get_client().table("sessions").update(update_data).eq("id", session_id).execute()
    data = result.data or []
    if not data:
        raise PersistenceError(f"Session '{session_id}' could not be updated")
    return data[0]


def get_session(session_id: str) -> dict[str, Any] | None:
    result = _get_client().table("sessions").select("*").eq("id", session_id).limit(1).execute()
    data = result.data or []
    return data[0] if data else None


def insert_task_log(
    *,
    task_id: str,
    session_id: str | None,
    event_type: str,
    status: str | None = None,
    step: str | None = None,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "task_id": task_id,
        "session_id": session_id,
        "event_type": event_type,
        "status": status,
        "step": step,
        "message": message,
        "payload": payload or {},
        "created_at": utc_now(),
    }
    result = _get_client().table("task_logs").insert(record).execute()
    return result.data[0] if result.data else record


def list_task_logs(task_id: str) -> list[dict[str, Any]]:
    result = (
        _get_client()
        .table("task_logs")
        .select("*")
        .eq("task_id", task_id)
        .order("created_at")
        .execute()
    )
    return list(result.data or [])
