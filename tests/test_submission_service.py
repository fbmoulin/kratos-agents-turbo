from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from src.core import ValidationError
from src.services.submission_service import SubmissionService


class _FakeUpload:
    def __init__(self, filename: str, content_type: str, content: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._content) - self._offset
        chunk = self._content[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_submit_batch_streams_uploads_without_materializing_file_bytes(monkeypatch):
    validator_service = SimpleNamespace(
        validate_batch_submission=lambda **kwargs: SimpleNamespace(
            message="Gerar lote",
            task_type="despacho",
            priority=9,
            requested_agent_id=None,
            idempotency_key=None,
            total_files=2,
        ),
        validate_upload_metadata=lambda **kwargs: SimpleNamespace(
            file_name=kwargs["file_name"],
            content_type="application/pdf",
        ),
        validate_file_size=lambda size: None,
        validate_batch_total_bytes=lambda total: None,
    )
    staged_calls: list[dict[str, object]] = []
    staging_service = SimpleNamespace(
        stage_upload_stream=lambda **kwargs: _raise_async_not_used(),
        delete_staged_inputs=lambda staged_paths: None,
    )

    async def fake_stage_upload_stream(**kwargs):
        staged_calls.append(kwargs)
        total = 0
        while True:
            chunk = await kwargs["upload_file"].read(4)
            if not chunk:
                break
            total += len(chunk)
        return {
            "staged_path": f"/tmp/{kwargs['task_id']}-{kwargs['file_name']}",
            "size_bytes": total,
        }

    staging_service.stage_upload_stream = fake_stage_upload_stream
    batch_service = SimpleNamespace(
        get_batch_by_idempotency_key=lambda key: None,
        create_batch_submission=lambda **kwargs: {
            "created": True,
            "batch": {"id": kwargs["batch_id"]},
            "tasks": [
                {
                    "id": item["task_id"],
                    "task_type": item["task_type"],
                }
                for item in kwargs["task_items"]
            ],
        },
        get_batch_with_tasks=lambda batch_id: None,
    )
    dispatch_service = SimpleNamespace(
        dispatch_tasks=lambda task_ids: {"dispatched": len(task_ids), "failed": 0},
        reconcile_pending=lambda: {"processed": 0, "dispatched": 0, "failed": 0},
    )

    service = SubmissionService(
        validator_service=validator_service,
        staging_service=staging_service,
        task_service=SimpleNamespace(),
        batch_service=batch_service,
        dispatch_service=dispatch_service,
        event_store=SimpleNamespace(),
        settings=SimpleNamespace(
            max_upload_bytes=1024,
            queue_for_task_type=lambda task_type: f"queue-{task_type}",
        ),
    )

    result = asyncio.run(
        service.submit_batch(
            files=[
                _FakeUpload("a.pdf", "application/pdf", b"1234"),
                _FakeUpload("b.pdf", "application/pdf", b"567890"),
            ],
            message="Gerar lote",
            task_type="despacho",
            priority=9,
            agent_id=None,
            idempotency_key=None,
        )
    )

    assert result["dispatch_summary"] == {"dispatched": 2, "failed": 0}
    assert len(staged_calls) == 2
    assert all("upload_file" in call for call in staged_calls)


def test_submit_batch_rejects_when_cumulative_size_exceeds_limit():
    deleted_paths: list[str] = []
    validator_service = SimpleNamespace(
        validate_batch_submission=lambda **kwargs: SimpleNamespace(
            message="Gerar lote",
            task_type="despacho",
            priority=9,
            requested_agent_id=None,
            idempotency_key=None,
            total_files=2,
        ),
        validate_upload_metadata=lambda **kwargs: SimpleNamespace(
            file_name=kwargs["file_name"],
            content_type="application/pdf",
        ),
        validate_file_size=lambda size: None,
        validate_batch_total_bytes=lambda total: (
            None
            if total <= 5
            else (_ for _ in ()).throw(
                ValidationError("Batch submission exceeds max cumulative size of 5 bytes")
            )
        ),
    )

    async def fake_stage_upload_stream(**kwargs):
        total = 0
        while True:
            chunk = await kwargs["upload_file"].read(4)
            if not chunk:
                break
            total += len(chunk)
        return {
            "staged_path": f"/tmp/{kwargs['task_id']}-{kwargs['file_name']}",
            "size_bytes": total,
        }

    service = SubmissionService(
        validator_service=validator_service,
        staging_service=SimpleNamespace(
            stage_upload_stream=fake_stage_upload_stream,
            delete_staged_input=lambda staged_path: deleted_paths.append(staged_path),
            delete_staged_inputs=lambda staged_paths: deleted_paths.extend(staged_paths),
        ),
        task_service=SimpleNamespace(),
        batch_service=SimpleNamespace(get_batch_by_idempotency_key=lambda key: None),
        dispatch_service=SimpleNamespace(),
        event_store=SimpleNamespace(),
        settings=SimpleNamespace(
            max_upload_bytes=1024,
            queue_for_task_type=lambda task_type: f"queue-{task_type}",
        ),
    )

    with pytest.raises(ValidationError, match="cumulative size"):
        asyncio.run(
            service.submit_batch(
                files=[
                    _FakeUpload("a.pdf", "application/pdf", b"123"),
                    _FakeUpload("b.pdf", "application/pdf", b"4567"),
                ],
                message="Gerar lote",
                task_type="despacho",
                priority=9,
                agent_id=None,
                idempotency_key=None,
            )
        )

    assert len(deleted_paths) >= 2


def _raise_async_not_used() -> None:
    raise AssertionError("stage_upload_stream should be replaced in test")
