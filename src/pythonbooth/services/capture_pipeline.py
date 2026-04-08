from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from ..models import CaptureJobRecord, CapturePayload, PhotoRecord, new_photo_id
from .backup_writer import write_backups
from .image_utils import (
    build_thumbnail,
    encode_qimage_to_jpeg_bytes,
    preview_bytes_from_data,
    preview_image_from_data,
    qimage_from_bytes,
    save_bytes,
    suffix_from_filename,
)
from .library import FilenameBuilder, SessionLibrary


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CapturePipeline:
    def __init__(
        self,
        session_library: SessionLibrary,
        *,
        backup_roots: list[str] | None = None,
        verify_backup_writes: bool = True,
    ) -> None:
        self.session_library = session_library
        self._backup_roots = [str(path).strip() for path in (backup_roots or []) if str(path).strip()]
        self._verify_backup_writes = bool(verify_backup_writes)

    def update_settings(self, *, backup_roots: list[str] | None = None, verify_backup_writes: bool | None = None) -> None:
        if backup_roots is not None:
            self._backup_roots = [str(path).strip() for path in backup_roots if str(path).strip()]
        if verify_backup_writes is not None:
            self._verify_backup_writes = bool(verify_backup_writes)

    def enqueue_capture(self, capture: CapturePayload) -> CaptureJobRecord:
        job_id = new_photo_id()
        payload_path = self.session_library.payloads_dir / f"{job_id}.bin"
        save_bytes(payload_path, capture.data)

        preview_payload = capture.preview_data or preview_bytes_from_data(
            capture.data,
            suffix=suffix_from_filename(capture.original_filename),
        )
        preview_payload_path: Path | None = None
        if preview_payload and preview_payload != capture.data:
            preview_payload_path = self.session_library.payloads_dir / f"{job_id}_preview.bin"
            save_bytes(preview_payload_path, preview_payload)

        job = CaptureJobRecord(
            id=job_id,
            source=capture.source,
            original_filename=capture.original_filename,
            created_at=_now_iso(),
            updated_at=_now_iso(),
            status="captured",
            session_sequence=self.session_library.next_session_sequence(),
            payload_path=str(payload_path),
            preview_payload_path=str(preview_payload_path) if preview_payload_path else None,
            camera_sequence=capture.camera_sequence,
            metadata=dict(capture.metadata),
        )
        self.session_library.upsert_job(job)
        self.session_library.mark_needs_recovery(needs_recovery=True)
        return job

    def process_capture(self, capture: CapturePayload, filename_builder: FilenameBuilder) -> PhotoRecord:
        job = self.enqueue_capture(capture)
        return self.process_job(job.id, filename_builder)

    def process_existing_file(self, path: Path, filename_builder: FilenameBuilder) -> PhotoRecord:
        capture = CapturePayload(
            data=path.read_bytes(),
            original_filename=path.name,
            source="hot-folder",
            captured_at=datetime.fromtimestamp(path.stat().st_mtime),
        )
        return self.process_capture(capture, filename_builder)

    def recover_pending_jobs(self, filename_builder: FilenameBuilder) -> list[PhotoRecord]:
        recovered: list[PhotoRecord] = []
        for job in self.session_library.recoverable_jobs():
            try:
                recovered.append(self.process_job(job.id, filename_builder))
            except Exception:
                continue
        return recovered

    def process_job(self, job_id: str, filename_builder: FilenameBuilder) -> PhotoRecord:
        job = self.session_library.get_job(job_id)
        if job is None:
            raise KeyError(f"Unknown capture job {job_id}")

        capture = self._read_capture(job)
        job = replace(job, attempt_count=job.attempt_count + 1, updated_at=_now_iso(), status="writing-primary", last_error="")
        plan = self.session_library.plan_capture(
            capture,
            filename_builder,
            session_sequence=job.session_sequence,
            final_name=job.final_filename or None,
        )
        job.final_filename = plan.final_name
        job.file_path = plan.final_path
        job.preview_path = plan.preview_path
        job.thumbnail_path = plan.thumbnail_path
        self.session_library.upsert_job(job)

        try:
            self._write_primary(Path(plan.final_path), capture.data)

            if plan.preview_path:
                job.status = "building-preview"
                job.updated_at = _now_iso()
                self.session_library.upsert_job(job)
                preview_bytes = None
                source_suffix = suffix_from_filename(capture.original_filename)
                if capture.preview_data and source_suffix.lower() not in {".cr2", ".cr3", ".raw"}:
                    preview_bytes = capture.preview_data
                elif capture.preview_data or source_suffix.lower() in {".cr2", ".cr3", ".raw"}:
                    preview_image = preview_image_from_data(
                        capture.data,
                        suffix=source_suffix,
                        preview_data=capture.preview_data,
                    )
                    if preview_image is not None and not preview_image.isNull():
                        preview_bytes = encode_qimage_to_jpeg_bytes(preview_image)
                elif qimage_from_bytes(capture.data) is not None:
                    preview_bytes = capture.data

                if preview_bytes:
                    self._write_primary(Path(plan.preview_path), preview_bytes)
                else:
                    job.preview_path = None

            job.status = "building-thumbnail"
            job.updated_at = _now_iso()
            self.session_library.upsert_job(job)
            thumb_source = Path(job.preview_path) if job.preview_path else Path(plan.final_path)
            build_thumbnail(thumb_source, Path(plan.thumbnail_path))

            record = self.session_library.build_record(capture, plan, record_id=job.record_id or new_photo_id())
            self.session_library.upsert_record(record)

            job.record_id = record.id
            job.thumbnail_path = record.thumbnail_path
            job.preview_path = record.preview_path
            job.status = "writing-backups"
            job.updated_at = _now_iso()
            self.session_library.upsert_job(job)
            job.backup_targets = write_backups(
                Path(plan.final_path),
                session_relative_path=self.session_library.session_relative_image_path(plan.final_path),
                backup_roots=self._backup_roots,
                verify=self._verify_backup_writes,
            )

            failed_backups = [result for result in job.backup_targets if result.status != "written"]
            job.status = "completed-with-warnings" if failed_backups else "completed"
            job.last_error = "; ".join(result.last_error for result in failed_backups if result.last_error)
            job.updated_at = _now_iso()
            self.session_library.upsert_job(job)
            self.session_library.remove_payload(job.payload_path)
            self.session_library.remove_payload(job.preview_payload_path)
            return record
        except Exception as exc:
            job.status = "failed"
            job.last_error = str(exc)
            job.updated_at = _now_iso()
            self.session_library.upsert_job(job)
            self.session_library.mark_needs_recovery(needs_recovery=True, last_error=str(exc))
            raise

    def queue_summary(self) -> dict[str, int]:
        pending = 0
        failed = 0
        warnings = 0
        for job in self.session_library.jobs:
            if job.status in {"captured", "writing-primary", "writing-backups", "building-preview", "building-thumbnail", "recovery-required"}:
                pending += 1
            elif job.status == "failed":
                failed += 1
            elif job.status == "completed-with-warnings":
                warnings += 1
        return {"pending": pending, "failed": failed, "warnings": warnings}

    @staticmethod
    def _write_primary(path: Path, data: bytes) -> None:
        if path.exists() and path.stat().st_size == len(data):
            return
        save_bytes(path, data)

    @staticmethod
    def _read_capture(job: CaptureJobRecord) -> CapturePayload:
        payload_path = Path(job.payload_path)
        data = payload_path.read_bytes()
        preview_data = None
        if job.preview_payload_path and Path(job.preview_payload_path).exists():
            preview_data = Path(job.preview_payload_path).read_bytes()
        return CapturePayload(
            data=data,
            preview_data=preview_data,
            original_filename=job.original_filename,
            source=job.source,
            camera_sequence=job.camera_sequence,
            captured_at=datetime.fromisoformat(job.created_at),
            metadata=dict(job.metadata),
        )
