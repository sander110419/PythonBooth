from datetime import datetime
from pathlib import Path

import numpy as np
from PyQt6.QtGui import QColor, QImage

from pythonbooth.models import CapturePayload
from pythonbooth.services.capture_pipeline import CapturePipeline
from pythonbooth.services.image_utils import encode_bgr_to_jpeg, encode_qimage_to_jpeg_bytes, extract_embedded_jpeg, load_preview_image
from pythonbooth.services.library import SessionLibrary


def _fake_raw_bytes() -> bytes:
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    frame[:, :] = (20, 180, 240)
    jpeg = encode_bgr_to_jpeg(frame, quality=92)
    assert jpeg is not None
    return b"CRAW\x00\x01garbage" + jpeg + b"\x00tail"


def test_extract_embedded_jpeg_from_fake_raw():
    preview = extract_embedded_jpeg(_fake_raw_bytes())

    assert preview is not None
    assert preview.startswith(b"\xff\xd8\xff")


def test_extract_embedded_jpeg_skips_unsupported_precision_candidates():
    unsupported_jpeg = (
        b"\xff\xd8"
        + b"\xff\xc0\x00\x11"
        + b"\x0e\x00\x10\x00\x10\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
        + b"\xff\xd9"
    )
    valid_preview = _fake_raw_bytes()

    preview = extract_embedded_jpeg(b"RAW" + unsupported_jpeg + b"noise" + valid_preview)

    assert preview is not None
    assert preview.startswith(b"\xff\xd8\xff")


def test_capture_pipeline_generates_preview_for_raw_capture(tmp_path: Path):
    library = SessionLibrary(tmp_path / "session")
    pipeline = CapturePipeline(library)
    capture = CapturePayload(
        data=_fake_raw_bytes(),
        original_filename="IMG_0001.CR3",
        source="simulator",
        captured_at=datetime(2026, 4, 8, 12, 0, 0),
        camera_sequence=1,
    )

    record = pipeline.process_capture(capture, lambda _capture, _seq: "raw_capture_0001.cr3")

    assert record.preview_path is not None
    assert Path(record.preview_path).exists()
    assert not load_preview_image(Path(record.preview_path)).isNull()


def test_load_preview_image_supports_raw_file_with_embedded_jpeg(tmp_path: Path):
    raw_path = tmp_path / "sample.CR2"
    raw_path.write_bytes(_fake_raw_bytes())

    image = load_preview_image(raw_path)

    assert not image.isNull()


def _jpeg_with_orientation(width: int, height: int, orientation: int) -> bytes:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#34c6b2"))
    jpeg = encode_qimage_to_jpeg_bytes(image)
    exif = (
        b"Exif\x00\x00"
        + b"II*\x00"
        + b"\x08\x00\x00\x00"
        + b"\x01\x00"
        + b"\x12\x01"
        + b"\x03\x00"
        + b"\x01\x00\x00\x00"
        + bytes([orientation, 0, 0, 0])
        + b"\x00\x00\x00\x00"
    )
    app1 = b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
    return jpeg[:2] + app1 + jpeg[2:]


def test_load_preview_image_applies_exif_rotation_for_jpeg(tmp_path: Path):
    jpeg_path = tmp_path / "rotated.jpg"
    jpeg_path.write_bytes(_jpeg_with_orientation(180, 120, orientation=6))

    image = load_preview_image(jpeg_path)

    assert not image.isNull()
    assert image.width() == 120
    assert image.height() == 180


def test_load_preview_image_applies_exif_rotation_for_embedded_raw_preview(tmp_path: Path):
    raw_path = tmp_path / "rotated.CR3"
    raw_path.write_bytes(b"CRAW\x00\x01garbage" + _jpeg_with_orientation(180, 120, orientation=6) + b"\x00tail")

    image = load_preview_image(raw_path)

    assert not image.isNull()
    assert image.width() == 120
    assert image.height() == 180


def _fake_cr2_with_orientation(orientation: int) -> bytes:
    tiff_header = (
        b"II*\x00"
        + b"\x08\x00\x00\x00"
        + b"\x01\x00"
        + b"\x12\x01"
        + b"\x03\x00"
        + b"\x01\x00\x00\x00"
        + bytes([orientation, 0, 0, 0])
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    return tiff_header + b"CR2DATA" + encode_qimage_to_jpeg_bytes(QImage(180, 120, QImage.Format.Format_RGB32))


def test_load_preview_image_applies_tiff_orientation_for_raw_preview(tmp_path: Path):
    raw_path = tmp_path / "rotated.CR2"
    image = QImage(180, 120, QImage.Format.Format_RGB32)
    image.fill(QColor("#34c6b2"))
    jpeg = encode_qimage_to_jpeg_bytes(image)
    tiff_header = (
        b"II*\x00"
        + b"\x08\x00\x00\x00"
        + b"\x01\x00"
        + b"\x12\x01"
        + b"\x03\x00"
        + b"\x01\x00\x00\x00"
        + b"\x08\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )
    raw_path.write_bytes(tiff_header + b"CR2DATA" + jpeg)

    rotated = load_preview_image(raw_path)

    assert not rotated.isNull()
    assert rotated.width() == 120
    assert rotated.height() == 180
