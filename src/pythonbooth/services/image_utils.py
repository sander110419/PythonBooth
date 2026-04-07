from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap


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
    thumb = QPixmap.fromImage(image).scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    thumb.save(str(thumb_path), "JPG", 88)
    return thumb_path


def placeholder_image(size: QSize, label: str = "RAW") -> QImage:
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#11151f"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(image.rect(), QColor("#11151f"))
    painter.setPen(QColor("#dbe4ff"))
    painter.setBrush(QColor(255, 255, 255, 18))
    inset = image.rect().adjusted(12, 12, -12, -12)
    painter.drawRoundedRect(inset, 18, 18)
    painter.setPen(QColor("#7fd6c2"))
    font = painter.font()
    font.setPointSize(max(14, image.height() // 7))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, label)
    painter.end()
    return image


def encode_qimage_to_jpeg_bytes(image: QImage, quality: int = 90) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG", quality)
    return bytes(buffer.data())
