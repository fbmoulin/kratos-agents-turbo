"""Local staging for uploaded documents before worker execution."""

from __future__ import annotations

from pathlib import Path

from src.core import ValidationError, get_settings


class StagingService:
    """Persist uploaded files to a shared local path for worker pickup."""

    chunk_size_bytes = 1024 * 1024

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

    async def stage_upload_stream(
        self,
        *,
        task_id: str,
        file_name: str,
        upload_file: object,
        max_bytes: int,
        batch_id: str | None = None,
    ) -> dict[str, object]:
        batch_segment = batch_id or "single"
        target_dir = self.base_path / batch_segment
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{task_id}-{file_name}"
        size_bytes = 0
        try:
            with target_path.open("wb") as handle:
                while True:
                    chunk = await upload_file.read(self.chunk_size_bytes)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > max_bytes:
                        raise ValidationError(
                            f"Uploaded file exceeds max size of {max_bytes} bytes"
                        )
                    handle.write(chunk)
            if size_bytes <= 0:
                raise ValidationError("Uploaded file is empty")
            return {
                "staged_path": str(target_path),
                "size_bytes": size_bytes,
            }
        except Exception:
            try:
                target_path.unlink()
            except FileNotFoundError:
                pass
            self._prune_empty_parents(target_dir)
            raise

    def load_staged_input(self, staged_path: str) -> bytes:
        path = Path(staged_path)
        if not path.exists():
            raise ValidationError(f"Staged input '{staged_path}' was not found")
        return path.read_bytes()

    def delete_staged_input(self, staged_path: str) -> None:
        path = Path(staged_path)
        try:
            path.unlink()
        except FileNotFoundError:
            return
        self._prune_empty_parents(path.parent)

    def delete_staged_inputs(self, staged_paths: list[str]) -> None:
        for staged_path in staged_paths:
            self.delete_staged_input(staged_path)

    def _prune_empty_parents(self, path: Path) -> None:
        current = path
        while current != self.base_path and current.is_dir():
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent


__all__ = ["StagingService"]
