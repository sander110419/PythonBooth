from datetime import datetime
from pathlib import Path

from pythonbooth.models import CapturePayload
from pythonbooth.services.capture_pipeline import CapturePipeline
from pythonbooth.services.library import SessionLibrary


def _capture() -> CapturePayload:
    return CapturePayload(
        data=b"jpeg-data",
        preview_data=b"preview-data",
        original_filename="IMG_0123.JPG",
        source="simulator",
        captured_at=datetime(2024, 4, 3, 10, 11, 12),
        camera_sequence=123,
    )


def test_session_library_and_pipeline_add_delete_capture(tmp_path: Path):
    library = SessionLibrary(tmp_path / "session")
    pipeline = CapturePipeline(library)

    record = pipeline.process_capture(_capture(), lambda _capture, _seq: "event_booth_00123.jpg")

    assert Path(record.file_path).exists()
    assert Path(record.preview_path).exists()
    assert Path(record.thumbnail_path).exists()
    assert library.get(record.id) is not None

    deleted = library.delete_photo(record.id)

    assert deleted is True
    assert library.get(record.id) is None


def test_session_library_marks_incomplete_jobs_for_recovery(tmp_path: Path):
    library = SessionLibrary(tmp_path / "session")
    pipeline = CapturePipeline(library)

    job = pipeline.enqueue_capture(_capture())

    reopened = SessionLibrary(tmp_path / "session")
    recovered = reopened.get_job(job.id)

    assert recovered is not None
    assert recovered.status == "recovery-required"


def test_session_library_rebuilds_missing_thumbnail_on_load(tmp_path: Path):
    library = SessionLibrary(tmp_path / "session")
    pipeline = CapturePipeline(library)
    record = pipeline.process_capture(_capture(), lambda _capture, _seq: "thumb_rebuild.jpg")

    thumb_path = Path(record.thumbnail_path)
    thumb_path.unlink()

    reopened = SessionLibrary(tmp_path / "session")
    refreshed = reopened.get(record.id)

    assert refreshed is not None
    assert refreshed.thumbnail_path is not None
    assert Path(refreshed.thumbnail_path).exists()
