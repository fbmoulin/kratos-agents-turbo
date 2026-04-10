"""Local staging for uploaded documents before worker execution."""

from __future__ import annotations

from pathlib import Path

from src.core import ValidationError, get_settings


class StagingService:
    """Persist uploaded files to a shared local path for worker pickup."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_path = self.settings.local_storage_path

    def stage_upload(
        self,
        *,
        task_id: str,
        file_name: str,
        file_bytes: bytes,
        batch_id: str | None = None,
    ) -> dict[str, object]:
        batch_segment = batch_id or "single"
        target_dir = self.base_path / batch_segment
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{task_id}-{file_name}"
        target_path.write_bytes(file_bytes)
        return {
            "staged_path": str(target_path),
            "size_bytes": len(file_bytes),
        }

    def load_staged_input(self, staged_path: str) -> bytes:
        path = Path(staged_path)
        if not path.exists():
            raise ValidationError(f"Staged input '{staged_path}' was not found")
        return path.read_bytes()


__all__ = ["StagingService"]
