from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from pythonbooth.config import AppConfig, ConfigStore
from pythonbooth.models import CapturePayload
from pythonbooth.services.image_utils import encode_qimage_to_jpeg_bytes
from pythonbooth.ui.main_window import MainWindow


def _app() -> QApplication:
    app = QApplication.instance()
    return app if app is not None else QApplication([])


def _sample_jpeg_bytes() -> bytes:
    image = QImage(180, 120, QImage.Format.Format_RGB32)
    image.fill(QColor("#34c6b2"))
    return encode_qimage_to_jpeg_bytes(image)


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


def test_new_secondary_window_receives_current_selection(tmp_path: Path):
    app = _app()
    config = AppConfig(
        backend="simulator",
        output_root=str(tmp_path / "sessions"),
        restore_last_session=False,
    )
    window = MainWindow(ConfigStore(tmp_path / "config.json"), config)

    try:
        window.show()
        capture = CapturePayload(
            data=_sample_jpeg_bytes(),
            original_filename="IMG_0001.JPG",
            source="simulator",
            captured_at=datetime(2026, 4, 8, 12, 0, 0),
            camera_sequence=1,
        )
        window._on_capture_ready(capture)
        app.processEvents()

        window._create_secondary_window()
        app.processEvents()

        secondary = window.secondary_windows[-1]
        assert secondary.windowTitle() != "Secondary Display"
        assert not secondary.viewer._pixmap_item.pixmap().isNull()
    finally:
        for secondary in list(window.secondary_windows):
            secondary.close()
        window.close()
        if window.camera_manager.isRunning():
            window.camera_manager.stop()
        app.processEvents()


def test_main_preview_stage_switches_to_portrait_aspect_ratio(tmp_path: Path):
    app = _app()
    config = AppConfig(
        backend="simulator",
        output_root=str(tmp_path / "sessions"),
        restore_last_session=False,
    )
    window = MainWindow(ConfigStore(tmp_path / "config.json"), config)

    try:
        window.show()
        window.resize(1500, 1000)
        capture = CapturePayload(
            data=_jpeg_with_orientation(180, 120, orientation=6),
            original_filename="IMG_0002.JPG",
            source="simulator",
            captured_at=datetime(2026, 4, 8, 12, 1, 0),
            camera_sequence=2,
        )
        window._on_capture_ready(capture)
        app.processEvents()

        assert abs(window.preview_stage._aspect_ratio - (2.0 / 3.0)) < 0.001
    finally:
        window.close()
        if window.camera_manager.isRunning():
            window.camera_manager.stop()
        app.processEvents()


def test_theme_background_applies_to_main_and_secondary_viewers(tmp_path: Path):
    app = _app()
    config = AppConfig(
        backend="simulator",
        background_color="#88ddee",
        output_root=str(tmp_path / "sessions"),
        restore_last_session=False,
    )
    window = MainWindow(ConfigStore(tmp_path / "config.json"), config)

    try:
        window.show()
        app.processEvents()

        assert window.preview_stage.viewer.backgroundBrush().color().name() == "#88ddee"

        window._create_secondary_window()
        app.processEvents()

        secondary = window.secondary_windows[-1]
        assert secondary.viewer.backgroundBrush().color().name() == "#88ddee"
    finally:
        for secondary in list(window.secondary_windows):
            secondary.close()
        window.close()
        if window.camera_manager.isRunning():
            window.camera_manager.stop()
        app.processEvents()
