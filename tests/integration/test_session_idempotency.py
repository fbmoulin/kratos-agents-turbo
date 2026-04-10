from __future__ import annotations

import os
import uuid

import redis
from src import db
from src.api.main import services as api_services


def test_session_service_reuses_canonical_session_for_same_task():
    task_id = str(uuid.uuid4())
    api_services.task_service.create_task(
        task_id=task_id,
        file_name="sample.pdf",
        task_type="despacho",
        message="Gerar minuta",
        priority=1,
        requested_agent_id=None,
        input_metadata={"content_type": "application/pdf"},
    )

    first_session = api_services.session_service.create_or_load_session(
        task_id=task_id,
        agent_id="legal-document-agent",
        requested_session_id=None,
        metadata={"file_name": "sample.pdf"},
    )
    second_session = api_services.session_service.create_or_load_session(
        task_id=task_id,
        agent_id="legal-document-agent",
        requested_session_id=None,
        metadata={"file_name": "sample.pdf"},
    )

    assert first_session["id"] == second_session["id"]
    assert db.get_session_by_task(task_id)["id"] == first_session["id"]
    with db.transaction() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "select count(*) as total from sessions where task_id = %s",
                (task_id,),
            )
            assert int(cursor.fetchone()["total"]) == 1


def test_redis_service_is_reachable():
    client = redis.Redis.from_url(
        os.environ["REDIS_URL"],
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    assert client.ping() is True
