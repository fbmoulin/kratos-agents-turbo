"""Celery tasks for processing judicial documents.

This module defines asynchronous tasks that will be executed by Celery
workers. The main task takes uploaded document bytes and performs
processing using an AI model to generate judicial decisions. It
manages task state via the database helper in ``src.db``.
"""

import base64
import os
import tempfile
import uuid
from typing import Optional

from celery import current_app, Task

from src import db

# Import your AI processing logic here. For demonstration purposes
# a simple placeholder is used. In a real deployment you would
# interact with your managed agents and RAG pipeline.


# Import your agent implementation. The LegalAgent combines
# simple skills (see src/skills) to perform classification and
# generate a basic decision text. In a real deployment this agent
# could interact with a managed agent or call an MCP server for
# additional tools.
from src.agent.legal_agent import LegalAgent


def ai_process_document(file_bytes: bytes, message: str) -> str:
    """Process a document using a simple legal agent.

    This helper wraps the ``LegalAgent`` class defined in
    ``src.agent.legal_agent``. It passes the raw file bytes and
    user message to the agent and returns the generated decision
    text. By isolating this logic in a function we keep
    ``process_document_task`` easy to read and open a clear
    extension point for integrating more sophisticated agents.

    :param file_bytes: raw bytes of the uploaded document
    :param message: user supplied message/instruction for the AI
    :returns: the generated decision text
    """
    agent = LegalAgent(file_bytes, message)
    return agent.run()


class BaseTask(Task):
    """Base Celery task that checks for cancellation before running.

    If a task has been marked as cancelled in the database, raising
    ``Ignore`` will prevent further processing and mark the task as
    revoked in Celery's backend. Subclasses should call
    ``self.check_cancelled(task_id)`` periodically.
    """

    def check_cancelled(self, task_id: str) -> None:
        record = db.get_task(task_id)
        if record and record.get("status") == "cancelled":
            # update Celery state but do not run further
            raise self.Ignore("Task was cancelled by user")


@current_app.task(bind=True, base=BaseTask, name="process_document")
def process_document_task(
    self,
    task_id: str,
    file_bytes: bytes,
    filename: str,
    message: str,
) -> str:
    """Asynchronous task to process a document.

    :param task_id: ID of the corresponding database task
    :param file_bytes: raw bytes of the uploaded document
    :param filename: original filename
    :param message: user supplied message/instruction for the AI
    :returns: the generated decision text
    """
    # Check if task is cancelled before starting
    self.check_cancelled(task_id)
    # Update DB: mark as running
    db.update_task_status(task_id, "running")
    db.insert_task_log(task_id, "running")

    try:
        # In this implementation we no longer need to save the file to
        # disk because our agent operates directly on the byte
        # content. If your AI pipeline requires a file path, you can
        # still write to a temporary file here. After writing you
        # should re‑check cancellation.

        # Re-check cancellation before processing
        self.check_cancelled(task_id)

        # Perform AI processing via the agent
        result_text = ai_process_document(file_bytes, message)

        # Re-check cancellation before finalising
        self.check_cancelled(task_id)

        # Update DB with result
        db.update_task_status(task_id, "done", result=result_text)
        db.insert_task_log(task_id, "done")
        return result_text

    except Exception as exc:
        # On any error update status to failed
        db.update_task_status(task_id, "failed", error=str(exc))
        db.insert_task_log(task_id, "failed")
        raise
    finally:
        # In this version we didn't write any temporary files, so
        # there is nothing to clean up. Keeping this block in place
        # allows for future modifications where a temp file might
        # still be created.
        pass