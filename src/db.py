"""Persistence helpers backed by direct PostgreSQL connections."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from src.core import PersistenceError, get_settings

_pool: ConnectionPool | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        if not settings.database_url:
            raise PersistenceError(
                "DATABASE_URL or SUPABASE_DB_URL must be configured before using persistence"
            )
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.database_min_pool_size,
            max_size=settings.database_max_pool_size,
            kwargs={
                "autocommit": True,
                "row_factory": dict_row,
            },
            open=True,
        )
    return _pool


@contextmanager
def transaction() -> Iterator[Any]:
    with _get_pool().connection() as conn:
        with conn.transaction():
            yield conn


def _json(value: dict[str, Any] | None) -> Json:
    return Json(value or {})


def _fetchone(
    query: str | sql.Composed,
    params: tuple[Any, ...] = (),
    *,
    conn: Any | None = None,
) -> dict[str, Any] | None:
    if conn is not None:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()
    with _get_pool().connection() as pooled:
        with pooled.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()


def _fetchall(
    query: str | sql.Composed,
    params: tuple[Any, ...] = (),
    *,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    if conn is not None:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall() or [])
    with _get_pool().connection() as pooled:
        with pooled.cursor() as cursor:
            cursor.execute(query, params)
            return list(cursor.fetchall() or [])


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
    batch_id: str | None = None,
    session_id: str | None = None,
    execution_mode: str = "document",
    input_metadata: dict[str, Any] | None = None,
    conn: Any | None = None,
) -> dict[str, Any]:
    query = """
        insert into tasks (
            id,
            batch_id,
            session_id,
            requested_agent_id,
            agent_id,
            file_name,
            task_type,
            status,
            message,
            priority,
            execution_mode,
            input_metadata,
            created_at,
            updated_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning *
    """
    return _fetchone(
        query,
        (
            task_id,
            batch_id,
            session_id,
            requested_agent_id,
            agent_id,
            file_name,
            task_type,
            status,
            message,
            priority,
            execution_mode,
            _json(input_metadata),
            utc_now(),
            utc_now(),
        ),
        conn=conn,
    ) or {}


def update_task(task_id: str, *, conn: Any | None = None, **fields: Any) -> dict[str, Any]:
    update_data = {**fields, "updated_at": utc_now()}
    assignments = [
        sql.SQL("{} = %s").format(sql.Identifier(column))
        for column in update_data.keys()
    ]
    values = [
        _json(value) if column in {"input_metadata", "output_metadata"} else value
        for column, value in update_data.items()
    ]
    query = sql.SQL("update tasks set {} where id = %s returning *").format(
        sql.SQL(", ").join(assignments)
    )
    result = _fetchone(query, (*values, task_id), conn=conn)
    if result is None:
        raise PersistenceError(f"Task '{task_id}' could not be updated")
    return result


def get_task(task_id: str, *, conn: Any | None = None) -> dict[str, Any] | None:
    return _fetchone("select * from tasks where id = %s limit 1", (task_id,), conn=conn)


def list_tasks(
    status: str | None = None,
    *,
    batch_id: str | None = None,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if batch_id:
        conditions.append("batch_id = %s")
        params.append(batch_id)
    query = "select * from tasks"
    if conditions:
        query += " where " + " and ".join(conditions)
    query += " order by created_at desc"
    return _fetchall(query, tuple(params), conn=conn)


def create_batch(
    *,
    batch_id: str,
    task_type: str,
    message: str,
    requested_agent_id: str | None,
    priority: int,
    total_tasks: int,
    input_metadata: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    conn: Any | None = None,
) -> dict[str, Any]:
    query = """
        insert into batches (
            id,
            task_type,
            message,
            requested_agent_id,
            priority,
            total_tasks,
            idempotency_key,
            input_metadata,
            created_at,
            updated_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning *
    """
    return _fetchone(
        query,
        (
            batch_id,
            task_type,
            message,
            requested_agent_id,
            priority,
            total_tasks,
            idempotency_key,
            _json(input_metadata),
            utc_now(),
            utc_now(),
        ),
        conn=conn,
    ) or {}


def get_batch(batch_id: str, *, conn: Any | None = None) -> dict[str, Any] | None:
    return _fetchone("select * from batches where id = %s limit 1", (batch_id,), conn=conn)


def get_batch_by_idempotency_key(
    idempotency_key: str,
    *,
    conn: Any | None = None,
) -> dict[str, Any] | None:
    return _fetchone(
        "select * from batches where idempotency_key = %s limit 1",
        (idempotency_key,),
        conn=conn,
    )


def list_batches(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall("select * from batches order by created_at desc", conn=conn)


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
    conn: Any | None = None,
) -> dict[str, Any]:
    query = """
        insert into sessions (
            id,
            task_id,
            agent_id,
            status,
            execution_mode,
            metadata,
            progress,
            current_step,
            created_at,
            updated_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning *
    """
    return _fetchone(
        query,
        (
            session_id,
            task_id,
            agent_id,
            status,
            execution_mode,
            _json(metadata),
            progress,
            current_step,
            utc_now(),
            utc_now(),
        ),
        conn=conn,
    ) or {}


def update_session(session_id: str, *, conn: Any | None = None, **fields: Any) -> dict[str, Any]:
    update_data = {**fields, "updated_at": utc_now()}
    assignments = [
        sql.SQL("{} = %s").format(sql.Identifier(column))
        for column in update_data.keys()
    ]
    values = [
        _json(value) if column == "metadata" else value
        for column, value in update_data.items()
    ]
    query = sql.SQL("update sessions set {} where id = %s returning *").format(
        sql.SQL(", ").join(assignments)
    )
    result = _fetchone(query, (*values, session_id), conn=conn)
    if result is None:
        raise PersistenceError(f"Session '{session_id}' could not be updated")
    return result


def get_session(session_id: str, *, conn: Any | None = None) -> dict[str, Any] | None:
    return _fetchone(
        "select * from sessions where id = %s limit 1",
        (session_id,),
        conn=conn,
    )


def insert_task_log(
    *,
    task_id: str,
    session_id: str | None,
    event_type: str,
    status: str | None = None,
    step: str | None = None,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
    conn: Any | None = None,
) -> dict[str, Any]:
    query = """
        insert into task_logs (
            task_id,
            session_id,
            event_type,
            status,
            step,
            message,
            payload,
            created_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning *
    """
    return _fetchone(
        query,
        (
            task_id,
            session_id,
            event_type,
            status,
            step,
            message,
            _json(payload),
            utc_now(),
        ),
        conn=conn,
    ) or {}


def list_task_logs(task_id: str, *, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        "select * from task_logs where task_id = %s order by created_at",
        (task_id,),
        conn=conn,
    )
