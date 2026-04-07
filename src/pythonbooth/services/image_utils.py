from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PyQt6.QtGui import QImage


SUPPORTED_IMPORT_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".cr2",
    ".cr3",
    ".raw",
}


def qimage_from_bytes(data: bytes) -> QImage | None:
    if not data:
        return None
    image = QImage.fromData(QByteArray(data))
    return image if not image.isNull() else None


def qimage_from_bgr(frame: np.ndarray) -> QImage | None:
    if frame is None or frame.size == 0:
        return None
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width, channels = rgb.shape
    bytes_per_line = channels * width
    return QImage(rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888).copy()


def encode_bgr_to_jpeg(frame: np.ndarray, quality: int = 95) -> bytes | None:
    if frame is None or frame.size == 0:
        return None
    ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return None
    return encoded.tobytes()


def suffix_from_filename(filename: str, fallback: str = ".jpg") -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix else fallback


def save_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def build_thumbnail(source_path: Path, thumb_path: Path, size: QSize = QSize(220, 160)) -> Path:
    image = QImage(str(source_path))
    if image.isNull():
        image = placeholder_image(size, label=source_path.suffix.upper().lstrip(".") or "FILE")
    thumb = image.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(str(thumb_path), "JPG", 88)
    return thumb_path


def placeholder_image(size: QSize, label: str = "RAW") -> QImage:
    canvas = np.zeros((max(1, size.height()), max(1, size.width()), 3), dtype=np.uint8)
    canvas[:, :] = (31, 21, 17)
    cv2.rectangle(canvas, (12, 12), (canvas.shape[1] - 12, canvas.shape[0] - 12), (90, 214, 198), 2)
    font_scale = max(0.6, min(canvas.shape[0], canvas.shape[1]) / 180.0)
    thickness = max(1, int(round(font_scale * 2)))
    text_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_DUPLEX, font_scale, thickness)
    origin = (
        max(10, (canvas.shape[1] - text_size[0]) // 2),
        max(text_size[1] + 10, (canvas.shape[0] + text_size[1]) // 2),
    )
    cv2.putText(canvas, label, origin, cv2.FONT_HERSHEY_DUPLEX, font_scale, (219, 228, 255), thickness, cv2.LINE_AA)
    return qimage_from_bgr(canvas) or QImage()


def encode_qimage_to_jpeg_bytes(image: QImage, quality: int = 90) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG", quality)
    return bytes(buffer.data())
