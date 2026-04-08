from datetime import datetime
from pathlib import Path

import pytest

from pythonbooth.models import CapturePayload
from pythonbooth.services.capture_pipeline import CapturePipeline
from pythonbooth.services.library import SessionLibrary


def _capture() -> CapturePayload:
    return CapturePayload(
        data=b"primary-bytes",
        preview_data=b"preview-bytes",
        original_filename="IMG_9001.JPG",
        source="simulator",
        captured_at=datetime(2024, 4, 3, 10, 11, 12),
        camera_sequence=9001,
    )


def test_capture_pipeline_writes_backup_copy(tmp_path: Path):
    session = SessionLibrary(tmp_path / "session")
    backup_root = tmp_path / "backup"
    pipeline = CapturePipeline(session, backup_roots=[str(backup_root)], verify_backup_writes=True)

    record = pipeline.process_capture(_capture(), lambda _capture, _seq: "event_09001.jpg")
    summary = pipeline.queue_summary()
    backup_file = backup_root / session.session_root.name / "images" / "event_09001.jpg"

    assert Path(record.file_path).exists()
    assert backup_file.exists()
    assert summary["pending"] == 0
    assert summary["failed"] == 0


def test_capture_pipeline_can_recover_persisted_job(tmp_path: Path):
    session = SessionLibrary(tmp_path / "session")
    pipeline = CapturePipeline(session)
    job = pipeline.enqueue_capture(_capture())

    reopened = SessionLibrary(tmp_path / "session")
    recovered_pipeline = CapturePipeline(reopened)
    records = recovered_pipeline.recover_pending_jobs(lambda _capture, _seq: "recover_09001.jpg")

    recovered_job = reopened.get_job(job.id)
    assert len(records) == 1
    assert recovered_job is not None
    assert recovered_job.status == "completed"
    assert Path(records[0].file_path).exists()


def test_capture_pipeline_marks_failure_when_primary_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    session = SessionLibrary(tmp_path / "session")
    pipeline = CapturePipeline(session)

    def _boom(_path: Path, _data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("pythonbooth.services.capture_pipeline.CapturePipeline._write_primary", staticmethod(_boom))

    with pytest.raises(OSError):
        pipeline.process_capture(_capture(), lambda _capture, _seq: "fail_09001.jpg")

    failed_jobs = [job for job in session.jobs if job.status == "failed"]
    assert failed_jobs
    assert "disk full" in failed_jobs[-1].last_error
