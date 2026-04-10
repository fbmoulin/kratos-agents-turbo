"""Input validation and sanitisation."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass

from src.core import ValidationError, get_settings


@dataclass(frozen=True)
class ValidatedTaskSubmission:
    file_name: str
    message: str
    task_type: str
    priority: int
    requested_agent_id: str | None
    requested_session_id: str | None
    content_type: str


class ValidatorService:
    """Validate API and worker payloads."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def validate_submission(
        self,
        *,
        file_bytes: bytes,
        file_name: str | None,
        content_type: str | None,
        message: str | None,
        task_type: str | None,
        priority: int | None,
        requested_agent_id: str | None,
        requested_session_id: str | None,
    ) -> ValidatedTaskSubmission:
        if not file_bytes:
            raise ValidationError("Uploaded file is empty")
        if len(file_bytes) > self.settings.max_upload_bytes:
            raise ValidationError(
                f"Uploaded file exceeds max size of {self.settings.max_upload_bytes} bytes"
            )

        safe_name = self._sanitize_filename(file_name or "document.pdf")
        mime_type = (content_type or "application/octet-stream").strip().lower()
        if not safe_name.lower().endswith(".pdf"):
            raise ValidationError("Only PDF files are supported in the current pipeline")
        if mime_type not in {"application/pdf", "application/octet-stream"}:
            raise ValidationError("Unsupported file content type")

        clean_message = (message or self.settings.default_task_message).strip()
        if not clean_message:
            raise ValidationError("Message must not be blank")
        if len(clean_message) > 4000:
            raise ValidationError("Message exceeds 4000 characters")

        clean_task_type = (task_type or self.settings.default_task_type).strip().lower()
        if clean_task_type not in self.settings.allowed_task_types:
            raise ValidationError(
                f"task_type must be one of: {', '.join(self.settings.allowed_task_types)}"
            )

        clean_priority = priority if priority is not None else 0
        if clean_priority < 0 or clean_priority > 10:
            raise ValidationError("priority must be between 0 and 10")

        if requested_session_id:
            try:
                uuid.UUID(requested_session_id)
            except ValueError as exc:
                raise ValidationError("session_id must be a valid UUID") from exc
            raise ValidationError(
                "session_id is not supported on POST /tasks yet; create-only submission is the only public mode"
            )

        return ValidatedTaskSubmission(
            file_name=safe_name,
            message=clean_message,
            task_type=clean_task_type,
            priority=clean_priority,
            requested_agent_id=requested_agent_id.strip() if requested_agent_id else None,
            requested_session_id=requested_session_id,
            content_type=mime_type,
        )

    @staticmethod
    def _sanitize_filename(file_name: str) -> str:
        base_name = os.path.basename(file_name).strip() or "document.pdf"
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name)
        sanitized = sanitized.strip("._") or "document.pdf"
        if not sanitized.lower().endswith(".pdf"):
            sanitized = f"{sanitized}.pdf"
        return sanitized
