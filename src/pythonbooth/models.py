from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class CapturePayload:
    data: bytes
    original_filename: str
    source: str
    preview_data: bytes | None = None
    captured_at: datetime = field(default_factory=datetime.now)
    camera_sequence: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PhotoRecord:
    id: str
    display_name: str
    file_path: str
    preview_path: str | None
    thumbnail_path: str | None
    captured_at: str
    source: str
    original_filename: str
    camera_sequence: int | None
    session_sequence: int
    deleted: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return Path(self.file_path)

    @property
    def preview(self) -> Path | None:
        return Path(self.preview_path) if self.preview_path else None

    @property
    def thumbnail(self) -> Path | None:
        return Path(self.thumbnail_path) if self.thumbnail_path else None


@dataclass(slots=True)
class CameraStatus:
    backend: str
    connected: bool
    state: str
    message: str
    camera_name: str = ""
    last_error: str = ""
    preview_available: bool = False
    available_cameras: list[str] = field(default_factory=list)
    updated_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def idle(cls, backend: str, message: str = "Idle") -> "CameraStatus":
        return cls(backend=backend, connected=False, state="idle", message=message)


def new_photo_id() -> str:
    return uuid4().hex
