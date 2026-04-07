from datetime import datetime
from pathlib import Path

from pythonbooth.models import CapturePayload
from pythonbooth.services.library import SessionLibrary


def test_session_library_adds_and_deletes_capture(tmp_path: Path):
    library = SessionLibrary(tmp_path / "session")
    capture = CapturePayload(
        data=b"jpeg-data",
        preview_data=b"preview-data",
        original_filename="IMG_0123.JPG",
        source="simulator",
        captured_at=datetime(2024, 4, 3, 10, 11, 12),
        camera_sequence=123,
    )

    record = library.add_capture(capture, lambda _capture, _seq: "event_booth_00123.jpg")

    assert Path(record.file_path).exists()
    assert Path(record.preview_path).exists()
    assert Path(record.thumbnail_path).exists()
    assert library.get(record.id) is not None

    deleted = library.delete_photo(record.id)

    assert deleted is True
    assert library.get(record.id) is None
