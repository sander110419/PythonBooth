from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..config import AppConfig
from ..models import (
    BackupTargetResult,
    CameraStatus,
    CaptureJobRecord,
    CapturePayload,
    CaptureWritePlan,
    PhotoRecord,
    SessionState,
    new_photo_id,
)
from .atomic_io import atomic_write_json
from .image_utils import build_thumbnail, suffix_from_filename


FilenameBuilder = Callable[[CapturePayload, int], str]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SessionLibrary:
    def __init__(self, session_root: Path):
        self.session_root = session_root
        self.images_dir = session_root / "images"
        self.previews_dir = session_root / "previews"
        self.thumbs_dir = session_root / "thumbs"
        self.queue_dir = session_root / "queue"
        self.payloads_dir = self.queue_dir / "payloads"
        self.index_path = session_root / "session.json"
        self.state_path = session_root / "session_state.json"
        self.jobs_path = session_root / "jobs.json"
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.previews_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        self.payloads_dir.mkdir(parents=True, exist_ok=True)
        self._records = self._load_records()
        self._jobs = self._load_jobs()
        self._state = self._load_state()
        self._reconcile()

    @property
    def records(self) -> list[PhotoRecord]:
        return list(self._records)

    @property
    def jobs(self) -> list[CaptureJobRecord]:
        return list(self._jobs)

    @property
    def state(self) -> SessionState:
        return self._state

    def _load_records(self) -> list[PhotoRecord]:
        if not self.index_path.exists():
            return []
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        records: list[PhotoRecord] = []
        for item in payload.get("photos", []):
            try:
                records.append(PhotoRecord(**item))
            except TypeError:
                continue
        return records

    def _load_jobs(self) -> list[CaptureJobRecord]:
        if not self.jobs_path.exists():
            return []
        payload = json.loads(self.jobs_path.read_text(encoding="utf-8"))
        jobs: list[CaptureJobRecord] = []
        for item in payload.get("jobs", []):
            backups = [BackupTargetResult(**backup) for backup in item.get("backup_targets", [])]
            item = dict(item)
            item["backup_targets"] = backups
            try:
                jobs.append(CaptureJobRecord(**item))
            except TypeError:
                continue
        return jobs

    def _load_state(self) -> SessionState:
        if self.state_path.exists():
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            valid = {field.name for field in SessionState.__dataclass_fields__.values()}
            filtered = {key: value for key, value in payload.items() if key in valid}
            return SessionState(**filtered)
        return SessionState(session_id=self.session_root.name, session_root=str(self.session_root))

    def _reconcile(self) -> None:
        changed_records = False
        valid_records: list[PhotoRecord] = []
        for record in self._records:
            file_path = Path(record.file_path)
            if not file_path.exists():
                changed_records = True
                continue
            if record.preview_path and not Path(record.preview_path).exists():
                record.preview_path = None
                changed_records = True
            thumb_source = Path(record.preview_path) if record.preview_path else file_path
            thumb_path = Path(record.thumbnail_path) if record.thumbnail_path else self.thumbs_dir / f"{Path(record.display_name).stem}.jpg"
            if not thumb_path.exists():
                build_thumbnail(thumb_source, thumb_path)
                record.thumbnail_path = str(thumb_path)
                changed_records = True
            valid_records.append(record)
        self._records = valid_records

        changed_jobs = False
        for job in self._jobs:
            if not job.is_terminal:
                job.status = "recovery-required"
                job.updated_at = _now_iso()
                if not job.last_error:
                    job.last_error = "Application closed before the capture job completed."
                changed_jobs = True

        if self._state.selected_photo_id and self.get(self._state.selected_photo_id) is None:
            self._state.selected_photo_id = ""
        self._state.active_job_ids = [job.id for job in self._jobs if not job.is_terminal]
        self._state.last_saved_at = _now_iso()

        if changed_records:
            self.save()
        if changed_jobs:
            self.save_jobs()
        self.save_state()

    def save(self) -> None:
        payload = {
            "saved_at": _now_iso(),
            "photos": [asdict(record) for record in self._records],
        }
        atomic_write_json(self.index_path, payload, indent=2)

    def save_jobs(self) -> None:
        payload = {
            "saved_at": _now_iso(),
            "jobs": [asdict(job) for job in self._jobs],
        }
        atomic_write_json(self.jobs_path, payload, indent=2)
        self._state.active_job_ids = [job.id for job in self._jobs if not job.is_terminal]
        self.save_state()

    def save_state(self) -> None:
        self._state.last_saved_at = _now_iso()
        atomic_write_json(self.state_path, asdict(self._state), indent=2)

    def next_session_sequence(self) -> int:
        max_record_sequence = max((record.session_sequence for record in self._records), default=0)
        max_job_sequence = max((job.session_sequence for job in self._jobs), default=0)
        return max(max_record_sequence, max_job_sequence) + 1

    def plan_capture(
        self,
        capture: CapturePayload,
        filename_builder: FilenameBuilder,
        *,
        session_sequence: int | None = None,
        final_name: str | None = None,
    ) -> CaptureWritePlan:
        session_sequence = session_sequence or self.next_session_sequence()
        requested_name = final_name or filename_builder(capture, session_sequence).strip()
        suffix = Path(requested_name).suffix.lower() or suffix_from_filename(capture.original_filename)
        if final_name:
            safe_name = final_name
        else:
            safe_name = self._unique_name(Path(requested_name).stem or f"capture_{session_sequence:05d}", suffix)
        final_path = self.images_dir / safe_name
        preview_path = self.previews_dir / f"{Path(safe_name).stem}_preview.jpg"
        thumb_path = self.thumbs_dir / f"{Path(safe_name).stem}.jpg"
        return CaptureWritePlan(
            session_sequence=session_sequence,
            final_name=safe_name,
            final_path=str(final_path),
            preview_path=str(preview_path),
            thumbnail_path=str(thumb_path),
        )

    def build_record(
        self,
        capture: CapturePayload,
        plan: CaptureWritePlan,
        *,
        record_id: str = "",
    ) -> PhotoRecord:
        return PhotoRecord(
            id=record_id or new_photo_id(),
            display_name=plan.final_name,
            file_path=plan.final_path,
            preview_path=plan.preview_path if plan.preview_path and Path(plan.preview_path).exists() else None,
            thumbnail_path=plan.thumbnail_path if Path(plan.thumbnail_path).exists() else None,
            captured_at=capture.captured_at.isoformat(timespec="seconds"),
            source=capture.source,
            original_filename=capture.original_filename,
            camera_sequence=capture.camera_sequence,
            session_sequence=plan.session_sequence,
            metadata=dict(capture.metadata),
        )

    def upsert_record(self, record: PhotoRecord) -> PhotoRecord:
        for index, existing in enumerate(self._records):
            if existing.id != record.id:
                continue
            self._records[index] = record
            self.save()
            return record
        self._records.append(record)
        self.save()
        return record

    def upsert_job(self, job: CaptureJobRecord) -> CaptureJobRecord:
        for index, existing in enumerate(self._jobs):
            if existing.id != job.id:
                continue
            self._jobs[index] = job
            self.save_jobs()
            return job
        self._jobs.append(job)
        self.save_jobs()
        return job

    def recoverable_jobs(self) -> list[CaptureJobRecord]:
        return [job for job in self._jobs if job.status in {"captured", "recovery-required", "failed"}]

    def update_context(self, session_id: str, config: AppConfig) -> None:
        self._state.session_id = session_id
        self._state.session_root = str(self.session_root)
        self._state.event_name = config.event_name
        self._state.booth_name = config.booth_name
        self._state.session_name = config.session_name
        self._state.naming_template = config.naming_template
        self.save_state()

    def set_selected_photo(self, photo_id: str) -> None:
        self._state.selected_photo_id = photo_id
        self.save_state()

    def set_camera_status(self, status: CameraStatus) -> None:
        self._state.last_camera_status = asdict(status)
        self.save_state()

    def mark_needs_recovery(self, *, needs_recovery: bool, last_error: str = "") -> None:
        self._state.needs_recovery = bool(needs_recovery)
        self._state.last_error = last_error
        self.save_state()

    def delete_photo(self, photo_id: str) -> bool:
        for index, record in enumerate(self._records):
            if record.id != photo_id:
                continue
            for maybe_path in (record.file_path, record.preview_path, record.thumbnail_path):
                if maybe_path:
                    path = Path(maybe_path)
                    if path.exists():
                        path.unlink()
            self._records.pop(index)
            for job in self._jobs:
                if job.record_id == photo_id:
                    job.status = "deleted"
                    job.updated_at = _now_iso()
            self.save()
            self.save_jobs()
            return True
        return False

    def get(self, photo_id: str) -> PhotoRecord | None:
        return next((record for record in self._records if record.id == photo_id), None)

    def get_job(self, job_id: str) -> CaptureJobRecord | None:
        return next((job for job in self._jobs if job.id == job_id), None)

    def session_relative_image_path(self, image_path: str | Path) -> Path:
        return Path(self.session_root.name) / "images" / Path(image_path).name

    def remove_payload(self, payload_path: str | None) -> None:
        if not payload_path:
            return
        path = Path(payload_path)
        if path.exists():
            path.unlink()

    def _unique_name(self, stem: str, suffix: str) -> str:
        candidate = f"{stem}{suffix}"
        index = 1
        while (self.images_dir / candidate).exists():
            candidate = f"{stem}_{index:02d}{suffix}"
            index += 1
        return candidate
