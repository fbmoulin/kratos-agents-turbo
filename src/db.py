"""Persistence helpers backed by direct PostgreSQL connections."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from src.core import PersistenceError, get_settings

_pool: ConnectionPool | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


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


def _json_default(value: Any) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _json(value: dict[str, Any] | None) -> Json:
    return Json(value or {}, dumps=lambda data: json.dumps(data, default=_json_default))


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
    return (
        _fetchone(
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
        )
        or {}
    )


def update_task(task_id: str, *, conn: Any | None = None, **fields: Any) -> dict[str, Any]:
    update_data = {**fields, "updated_at": utc_now()}
    assignments = [
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in update_data.keys()
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
    return (
        _fetchone(
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
        )
        or {}
    )


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


def list_batch_summaries(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        with batch_counts as (
            select
                b.id,
                b.task_type,
                b.message,
                b.requested_agent_id,
                b.priority,
                b.total_tasks,
                b.idempotency_key,
                b.input_metadata,
                b.created_at,
                b.updated_at,
                count(*) filter (where t.status = 'queued') as queued_count,
                count(*) filter (where t.status = 'running') as running_count,
                count(*) filter (where t.status = 'completed') as completed_count,
                count(*) filter (where t.status = 'failed') as failed_count,
                count(*) filter (where t.status = 'cancelled') as cancelled_count
            from batches b
            left join tasks t on t.batch_id = b.id
            group by
                b.id,
                b.task_type,
                b.message,
                b.requested_agent_id,
                b.priority,
                b.total_tasks,
                b.idempotency_key,
                b.input_metadata,
                b.created_at,
                b.updated_at
        )
        select
            id,
            task_type,
            message,
            requested_agent_id,
            priority,
            total_tasks,
            idempotency_key,
            input_metadata,
            created_at,
            updated_at,
            case
                when cancelled_count = total_tasks then 'cancelled'
                when completed_count = total_tasks then 'completed'
                when failed_count = total_tasks then 'failed'
                when queued_count = total_tasks then 'queued'
                when running_count > 0 or queued_count > 0 then 'running'
                else 'partial'
            end as status,
            queued_count::bigint as queued_count,
            running_count::bigint as running_count,
            completed_count::bigint as completed_count,
            failed_count::bigint as failed_count,
            cancelled_count::bigint as cancelled_count
        from batch_counts
        order by created_at desc
        """,
        conn=conn,
    )


def get_batch_summary(batch_id: str, *, conn: Any | None = None) -> dict[str, Any] | None:
    return _fetchone(
        """
        with batch_counts as (
            select
                b.id,
                b.task_type,
                b.message,
                b.requested_agent_id,
                b.priority,
                b.total_tasks,
                b.idempotency_key,
                b.input_metadata,
                b.created_at,
                b.updated_at,
                count(*) filter (where t.status = 'queued') as queued_count,
                count(*) filter (where t.status = 'running') as running_count,
                count(*) filter (where t.status = 'completed') as completed_count,
                count(*) filter (where t.status = 'failed') as failed_count,
                count(*) filter (where t.status = 'cancelled') as cancelled_count
            from batches b
            left join tasks t on t.batch_id = b.id
            where b.id = %s
            group by
                b.id,
                b.task_type,
                b.message,
                b.requested_agent_id,
                b.priority,
                b.total_tasks,
                b.idempotency_key,
                b.input_metadata,
                b.created_at,
                b.updated_at
        )
        select
            id,
            task_type,
            message,
            requested_agent_id,
            priority,
            total_tasks,
            idempotency_key,
            input_metadata,
            created_at,
            updated_at,
            case
                when cancelled_count = total_tasks then 'cancelled'
                when completed_count = total_tasks then 'completed'
                when failed_count = total_tasks then 'failed'
                when queued_count = total_tasks then 'queued'
                when running_count > 0 or queued_count > 0 then 'running'
                else 'partial'
            end as status,
            queued_count::bigint as queued_count,
            running_count::bigint as running_count,
            completed_count::bigint as completed_count,
            failed_count::bigint as failed_count,
            cancelled_count::bigint as cancelled_count
        from batch_counts
        """,
        (batch_id,),
        conn=conn,
    )


def list_batch_task_views(batch_id: str, *, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            id,
            file_name,
            status,
            priority,
            session_id,
            coalesce((input_metadata ->> 'batch_item_index')::int, 0) as batch_item_index,
            created_at
        from tasks
        where batch_id = %s
        order by batch_item_index asc, created_at asc
        """,
        (batch_id,),
        conn=conn,
    )


def list_open_batch_summaries(
    *,
    limit: int = 25,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    return _fetchall(
        """
        with batch_counts as (
            select
                b.id,
                b.task_type,
                b.message,
                b.requested_agent_id,
                b.priority,
                b.total_tasks,
                b.idempotency_key,
                b.input_metadata,
                b.created_at,
                b.updated_at,
                count(*) filter (where t.status = 'queued') as queued_count,
                count(*) filter (where t.status = 'running') as running_count,
                count(*) filter (where t.status = 'completed') as completed_count,
                count(*) filter (where t.status = 'failed') as failed_count,
                count(*) filter (where t.status = 'cancelled') as cancelled_count
            from batches b
            left join tasks t on t.batch_id = b.id
            group by
                b.id,
                b.task_type,
                b.message,
                b.requested_agent_id,
                b.priority,
                b.total_tasks,
                b.idempotency_key,
                b.input_metadata,
                b.created_at,
                b.updated_at
        )
        select
            id,
            task_type,
            message,
            requested_agent_id,
            priority,
            total_tasks,
            idempotency_key,
            input_metadata,
            created_at,
            updated_at,
            case
                when cancelled_count = total_tasks then 'cancelled'
                when completed_count = total_tasks then 'completed'
                when failed_count = total_tasks then 'failed'
                when queued_count = total_tasks then 'queued'
                when running_count > 0 or queued_count > 0 then 'running'
                else 'partial'
            end as status,
            queued_count::bigint as queued_count,
            running_count::bigint as running_count,
            completed_count::bigint as completed_count,
            failed_count::bigint as failed_count,
            cancelled_count::bigint as cancelled_count
        from batch_counts
        where
            case
                when cancelled_count = total_tasks then 'cancelled'
                when completed_count = total_tasks then 'completed'
                when failed_count = total_tasks then 'failed'
                when queued_count = total_tasks then 'queued'
                when running_count > 0 or queued_count > 0 then 'running'
                else 'partial'
            end in ('queued', 'running', 'partial')
        order by created_at desc
        limit %s
        """,
        (limit,),
        conn=conn,
    )


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
    return (
        _fetchone(
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
        )
        or {}
    )


def update_session(session_id: str, *, conn: Any | None = None, **fields: Any) -> dict[str, Any]:
    update_data = {**fields, "updated_at": utc_now()}
    assignments = [
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in update_data.keys()
    ]
    values = [
        _json(value) if column == "metadata" else value for column, value in update_data.items()
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


def get_session_by_task_id(task_id: str, *, conn: Any | None = None) -> dict[str, Any] | None:
    return _fetchone(
        "select * from sessions where task_id = %s limit 1",
        (task_id,),
        conn=conn,
    )


def get_session_by_task(task_id: str, *, conn: Any | None = None) -> dict[str, Any] | None:
    return _fetchone(
        "select * from sessions where task_id = %s limit 1",
        (task_id,),
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
    return (
        _fetchone(
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
        )
        or {}
    )


def list_task_logs(task_id: str, *, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        "select * from task_logs where task_id = %s order by created_at",
        (task_id,),
        conn=conn,
    )


def create_task_dispatch(
    *,
    task_id: str,
    queue_name: str,
    payload: dict[str, Any],
    status: str = "pending",
    conn: Any | None = None,
) -> dict[str, Any]:
    query = """
        insert into task_dispatches (
            task_id,
            queue_name,
            status,
            payload,
            attempts,
            created_at,
            updated_at
        )
        values (%s, %s, %s, %s, 0, %s, %s)
        returning *
    """
    return (
        _fetchone(
            query,
            (
                task_id,
                queue_name,
                status,
                _json(payload),
                utc_now(),
                utc_now(),
            ),
            conn=conn,
        )
        or {}
    )


def get_task_dispatch(task_id: str, *, conn: Any | None = None) -> dict[str, Any] | None:
    return _fetchone(
        "select * from task_dispatches where task_id = %s limit 1",
        (task_id,),
        conn=conn,
    )


def list_task_dispatches(
    *,
    statuses: tuple[str, ...] = ("pending", "failed"),
    limit: int = 100,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    if not statuses:
        return []
    placeholders = ", ".join(["%s"] * len(statuses))
    query = f"""
        select * from task_dispatches
        where status in ({placeholders})
        order by created_at
        limit %s
    """
    return _fetchall(query, (*statuses, limit), conn=conn)


def claim_task_dispatch(task_id: str, *, conn: Any | None = None) -> dict[str, Any] | None:
    result = _fetchone(
        """
        update task_dispatches
        set
            status = 'dispatching',
            updated_at = %s
        where task_id = %s
          and status in ('pending', 'failed')
        returning *
        """,
        (utc_now(), task_id),
        conn=conn,
    )
    if result is not None:
        return result
    return get_task_dispatch(task_id, conn=conn)


def claim_task_dispatches(
    *,
    statuses: tuple[str, ...] = ("pending", "failed"),
    limit: int = 100,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    if not statuses:
        return []
    if conn is None:
        with transaction() as tx:
            return claim_task_dispatches(statuses=statuses, limit=limit, conn=tx)

    placeholders = ", ".join(["%s"] * len(statuses))
    query = f"""
        with locked as (
            select task_id
            from task_dispatches
            where status in ({placeholders})
            order by created_at
            for update skip locked
            limit %s
        )
        update task_dispatches td
        set
            status = 'dispatching',
            updated_at = %s
        from locked
        where td.task_id = locked.task_id
        returning td.*
    """
    return _fetchall(query, (*statuses, limit, utc_now()), conn=conn)


def update_task_dispatch(
    task_id: str,
    *,
    conn: Any | None = None,
    **fields: Any,
) -> dict[str, Any]:
    update_data = {**fields, "updated_at": utc_now()}
    assignments = [
        sql.SQL("{} = %s").format(sql.Identifier(column)) for column in update_data.keys()
    ]
    values = [
        _json(value) if column == "payload" else value for column, value in update_data.items()
    ]
    query = sql.SQL("update task_dispatches set {} where task_id = %s returning *").format(
        sql.SQL(", ").join(assignments)
    )
    result = _fetchone(query, (*values, task_id), conn=conn)
    if result is None:
        raise PersistenceError(f"Task dispatch '{task_id}' could not be updated")
    return result


def get_task_event_counts(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            t.task_type,
            l.event_type,
            count(*)::bigint as total
        from task_logs l
        join tasks t on t.id = l.task_id
        group by t.task_type, l.event_type
        order by t.task_type, l.event_type
        """,
        conn=conn,
    )


def get_task_status_counts(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            task_type,
            status,
            count(*)::bigint as total
        from tasks
        group by task_type, status
        order by task_type, status
        """,
        conn=conn,
    )


def get_batch_status_counts(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        with batch_counts as (
            select
                b.id,
                b.task_type,
                b.total_tasks,
                count(*) filter (where t.status = 'queued') as queued_count,
                count(*) filter (where t.status = 'running') as running_count,
                count(*) filter (where t.status = 'completed') as completed_count,
                count(*) filter (where t.status = 'failed') as failed_count,
                count(*) filter (where t.status = 'cancelled') as cancelled_count
            from batches b
            left join tasks t on t.batch_id = b.id
            group by b.id, b.task_type, b.total_tasks
        )
        select
            task_type,
            case
                when cancelled_count = total_tasks then 'cancelled'
                when completed_count = total_tasks then 'completed'
                when failed_count = total_tasks then 'failed'
                when queued_count = total_tasks then 'queued'
                when running_count > 0 or queued_count > 0 then 'running'
                else 'partial'
            end as status,
            count(*)::bigint as total
        from batch_counts
        group by task_type, status
        order by task_type, status
        """,
        conn=conn,
    )


def get_dispatch_status_counts(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            status,
            count(*)::bigint as total
        from task_dispatches
        group by status
        order by status
        """,
        conn=conn,
    )


def get_task_duration_stats(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            task_type,
            status,
            count(*)::bigint as total,
            coalesce(
                avg(extract(epoch from (finished_at - started_at))),
                0
            )::double precision as avg_seconds,
            coalesce(
                max(extract(epoch from (finished_at - started_at))),
                0
            )::double precision as max_seconds
        from tasks
        where started_at is not null and finished_at is not null
        group by task_type, status
        order by task_type, status
        """,
        conn=conn,
    )


def get_last_success_timestamps(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            task_type,
            extract(epoch from max(finished_at))::double precision as finished_at_epoch
        from tasks
        where status = 'completed'
          and finished_at is not null
        group by task_type
        order by task_type
        """,
        conn=conn,
    )


def list_pending_dispatches(
    *,
    older_than_minutes: int,
    limit: int = 100,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            td.task_id,
            td.queue_name,
            td.status,
            td.attempts,
            td.last_error,
            td.created_at,
            td.updated_at,
            td.dispatched_at,
            t.batch_id,
            t.task_type,
            t.file_name
        from task_dispatches td
        join tasks t on t.id = td.task_id
        where td.status in ('pending', 'failed', 'dispatching')
          and td.updated_at <= now() - make_interval(mins => %s)
        order by td.updated_at asc
        limit %s
        """,
        (older_than_minutes, limit),
        conn=conn,
    )


def list_stuck_tasks(
    *,
    older_than_minutes: int,
    limit: int = 100,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            id,
            batch_id,
            session_id,
            task_type,
            file_name,
            status,
            priority,
            started_at,
            updated_at
        from tasks
        where status = 'running'
          and started_at <= now() - make_interval(mins => %s)
        order by started_at asc
        limit %s
        """,
        (older_than_minutes, limit),
        conn=conn,
    )


def list_dispatched_but_queued_tasks(
    *,
    older_than_minutes: int,
    limit: int = 100,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            t.id,
            t.batch_id,
            t.session_id,
            t.task_type,
            t.file_name,
            t.status,
            t.priority,
            td.queue_name,
            td.dispatched_at,
            td.updated_at
        from tasks t
        join task_dispatches td on td.task_id = t.id
        where t.status = 'queued'
          and td.status = 'dispatched'
          and coalesce(td.dispatched_at, td.updated_at) <= now() - make_interval(mins => %s)
        order by coalesce(td.dispatched_at, td.updated_at) asc
        limit %s
        """,
        (older_than_minutes, limit),
        conn=conn,
    )


def get_failed_task_counts(*, conn: Any | None = None) -> list[dict[str, Any]]:
    return _fetchall(
        """
        select
            task_type,
            count(*)::bigint as total
        from tasks
        where status = 'failed'
        group by task_type
        order by task_type
        """,
        conn=conn,
    )


def count_pending_dispatches(*, conn: Any | None = None) -> int:
    result = _fetchone(
        """
        select count(*)::bigint as total
        from task_dispatches
        where status in ('pending', 'failed', 'dispatching')
        """,
        conn=conn,
    )
    return int((result or {}).get("total") or 0)


def count_running_tasks(*, conn: Any | None = None) -> int:
    result = _fetchone(
        """
        select count(*)::bigint as total
        from tasks
        where status = 'running'
        """,
        conn=conn,
    )
    return int((result or {}).get("total") or 0)
