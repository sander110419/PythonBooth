from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

RAW_RECORD_SUFFIXES = {".cr2", ".cr3", ".raw"}


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

    @property
    def is_raw(self) -> bool:
        return self.path.suffix.lower() in RAW_RECORD_SUFFIXES

    @property
    def display_preview_source(self) -> Path:
        return self.preview or self.path


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
    retry_in_seconds: float = 0.0
    reconnect_attempts: int = 0
    recoverable: bool = True
    updated_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def idle(cls, backend: str, message: str = "Idle") -> "CameraStatus":
        return cls(backend=backend, connected=False, state="idle", message=message)


def new_photo_id() -> str:
    return uuid4().hex


@dataclass(slots=True)
class BackupTargetResult:
    root: str
    target_path: str
    status: str
    verified: bool = False
    size: int = 0
    last_error: str = ""


@dataclass(slots=True)
class CaptureJobRecord:
    id: str
    source: str
    original_filename: str
    created_at: str
    updated_at: str
    status: str
    session_sequence: int
    payload_path: str
    preview_payload_path: str | None = None
    camera_sequence: int | None = None
    final_filename: str = ""
    file_path: str = ""
    preview_path: str | None = None
    thumbnail_path: str | None = None
    record_id: str = ""
    backup_targets: list[BackupTargetResult] = field(default_factory=list)
    attempt_count: int = 0
    last_error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in {"completed", "completed-with-warnings", "failed", "deleted"}


@dataclass(slots=True)
class SessionState:
    session_id: str
    session_root: str
    selected_photo_id: str = ""
    event_name: str = ""
    booth_name: str = ""
    session_name: str = ""
    naming_template: str = ""
    last_camera_status: dict[str, Any] = field(default_factory=dict)
    active_job_ids: list[str] = field(default_factory=list)
    last_saved_at: str = ""
    needs_recovery: bool = False
    last_error: str = ""


@dataclass(slots=True)
class CaptureWritePlan:
    session_sequence: int
    final_name: str
    final_path: str
    preview_path: str | None
    thumbnail_path: str


@dataclass(slots=True)
class PreflightCheckResult:
    name: str
    severity: str
    message: str
    details: str = ""


@dataclass(slots=True)
class PreflightReport:
    generated_at: str
    overall_status: str
    checks: list[PreflightCheckResult] = field(default_factory=list)

    @property
    def failed(self) -> list[PreflightCheckResult]:
        return [check for check in self.checks if check.severity == "fail"]

    @property
    def warnings(self) -> list[PreflightCheckResult]:
        return [check for check in self.checks if check.severity == "warn"]
