"""Database integration for task management.

The functions in this module provide a simple abstraction over
Supabase's REST interface to store and retrieve tasks. If you
configure your Supabase instance URL and API key via the environment
variables ``SUPABASE_URL`` and ``SUPABASE_KEY`` the functions
defined here will automatically connect to your database.

If those environment variables are not set, the functions will raise
RuntimeError. See ``README.md`` for more details on how to set up
your Supabase project.

To minimise dependencies this module uses the official ``supabase``
client. If that package is not installed you can install it with
``pip install supabase``.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from supabase import create_client, Client

_client: Optional[Client] = None


def _get_client() -> Client:
    """Lazily create a Supabase client using environment variables.

    :raises RuntimeError: if required env vars are missing.
    :return: supabase client
    """
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY environment variables must be set"
            )
        _client = create_client(url, key)
    return _client


def insert_task(
    task_id: str,
    file_name: str,
    tipo: str,
    status: str,
    priority: int = 0,
) -> None:
    """Insert a new task record into the ``tasks`` table.

    :param task_id: unique identifier for the task
    :param file_name: original name of the uploaded file
    :param tipo: type of decision (despacho, decisao, sentenca)
    :param status: initial status of the task
    :param priority: optional priority value
    :raises: any exceptions raised by the supabase client
    """
    client = _get_client()
    now = datetime.utcnow().isoformat()
    payload = {
        "id": task_id,
        "file_name": file_name,
        "tipo": tipo,
        "status": status,
        "priority": priority,
        "created_at": now,
    }
    client.table("tasks").insert(payload).execute()


def update_task_status(task_id: str, status: str, result: Optional[str] = None, error: Optional[str] = None) -> None:
    """Update the status and optionally result/error of a task.

    :param task_id: id of task to update
    :param status: new status string
    :param result: optional result text
    :param error: optional error text
    """
    client = _get_client()
    update_data: Dict[str, Any] = {"status": status}
    if result is not None:
        update_data["result"] = result
        update_data["finished_at"] = datetime.utcnow().isoformat()
    if error is not None:
        update_data["error"] = error
        update_data["finished_at"] = datetime.utcnow().isoformat()
    client.table("tasks").update(update_data).eq("id", task_id).execute()


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single task by its id.

    :param task_id: unique identifier
    :return: task dict or None if not found
    """
    client = _get_client()
    res = client.table("tasks").select("*").eq("id", task_id).execute()
    data = res.data
    return data[0] if data else None


def list_tasks(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return a list of all tasks or filter by status.

    :param status: optional status to filter by
    :return: list of task dicts
    """
    client = _get_client()
    query = client.table("tasks").select("*")
    if status:
        query = query.eq("status", status)
    return query.execute().data


def insert_task_log(task_id: str, step: str) -> None:
    """Insert a record into the ``task_logs`` table for auditing.

    :param task_id: id of the task
    :param step: textual description of current step or event
    """
    client = _get_client()
    payload = {"task_id": task_id, "step": step}
    client.table("task_logs").insert(payload).execute()
