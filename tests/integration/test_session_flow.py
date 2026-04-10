from __future__ import annotations

import threading
import uuid

from src import db
from src.services.session_service import SessionService
from src.session import SessionManager


def test_create_or_load_session_reuses_canonical_task_session_under_concurrency():
    task_id = str(uuid.uuid4())
    db.create_task(
        task_id=task_id,
        file_name="task.pdf",
        task_type="despacho",
        status="queued",
        message="Emitir minuta",
        priority=1,
        requested_agent_id="legal-document-agent",
        input_metadata={"staged_path": f"/tmp/{task_id}.pdf"},
    )

    service = SessionService(session_manager=SessionManager())
    session_ids: list[str] = []
    lock = threading.Lock()

    def load_or_create() -> None:
        session = service.create_or_load_session(
            task_id=task_id,
            agent_id="legal-document-agent",
            requested_session_id=None,
            execution_mode="document",
            metadata={"content_type": "application/pdf"},
        )
        with lock:
            session_ids.append(session["id"])

    threads = [threading.Thread(target=load_or_create) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows = db._fetchall("select id from sessions where task_id = %s", (task_id,))

    assert len(set(session_ids)) == 1
    assert len(rows) == 1
