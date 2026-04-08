from __future__ import annotations

import struct
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PyQt6.QtGui import QImage, QImageReader, QTransform

from .atomic_io import atomic_write_bytes


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

RAW_SUFFIXES = {".cr2", ".cr3", ".raw"}
_JPEG_SOI = b"\xff\xd8"
_JPEG_EXIF_MARKER = b"Exif\x00\x00"
_EXIF_ORIENTATION_TAG = 0x0112
_JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


def qimage_from_bytes(data: bytes) -> QImage | None:
    if not data:
        return None
    buffer = QBuffer()
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    image = reader.read()
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
    atomic_write_bytes(path, data)


def extract_embedded_jpeg(data: bytes) -> bytes | None:
    if not data:
        return None
    best: bytes | None = None
    start = 0
    while True:
        soi = data.find(b"\xff\xd8\xff", start)
        if soi < 0:
            break
        eoi = data.find(b"\xff\xd9", soi + 3)
        if eoi < 0:
            break
        candidate = data[soi : eoi + 2]
        sample_precision = _extract_jpeg_sample_precision(candidate)
        if sample_precision is not None and sample_precision != 8:
            start = soi + 3
            continue
        image = qimage_from_bytes(candidate)
        if image is not None and not image.isNull():
            if best is None or len(candidate) > len(best):
                best = candidate
        start = soi + 3
    return best


def extract_orientation_from_data(data: bytes, *, suffix: str = "") -> int | None:
    if not data:
        return None

    jpeg_orientation = _extract_jpeg_orientation(data)
    if jpeg_orientation is not None:
        return jpeg_orientation

    normalized_suffix = suffix.lower()
    if normalized_suffix in {".cr2", ".tif", ".tiff"}:
        tiff_orientation = _extract_tiff_orientation(data, 0)
        if tiff_orientation is not None:
            return tiff_orientation

    search_limit = min(len(data), 4 * 1024 * 1024)
    for marker in (b"Exif\x00\x00II*\x00", b"Exif\x00\x00MM\x00*"):
        start = 0
        while True:
            offset = data.find(marker, start, search_limit)
            if offset < 0:
                break
            tiff_orientation = _extract_tiff_orientation(data, offset + len(_JPEG_EXIF_MARKER))
            if tiff_orientation is not None:
                return tiff_orientation
            start = offset + 1
    return None


def apply_orientation(image: QImage, orientation: int | None) -> QImage:
    if image.isNull() or orientation in {None, 1}:
        return image
    if orientation == 2:
        return image.mirrored(True, False)
    if orientation == 3:
        return image.transformed(QTransform().rotate(180))
    if orientation == 4:
        return image.mirrored(False, True)
    if orientation == 5:
        return image.mirrored(True, False).transformed(QTransform().rotate(90))
    if orientation == 6:
        return image.transformed(QTransform().rotate(90))
    if orientation == 7:
        return image.mirrored(True, False).transformed(QTransform().rotate(-90))
    if orientation == 8:
        return image.transformed(QTransform().rotate(-90))
    return image


def preview_image_from_data(data: bytes, *, suffix: str = "", preview_data: bytes | None = None) -> QImage | None:
    normalized_suffix = suffix.lower()
    if normalized_suffix not in RAW_SUFFIXES:
        return qimage_from_bytes(preview_data or data)

    embedded_preview = preview_data or extract_embedded_jpeg(data)
    if not embedded_preview:
        return None

    image = qimage_from_bytes(embedded_preview)
    if image is None or image.isNull():
        return None

    preview_orientation = extract_orientation_from_data(embedded_preview, suffix=".jpg")
    raw_orientation = extract_orientation_from_data(data, suffix=normalized_suffix)
    if raw_orientation not in {None, 1} and preview_orientation in {None, 1}:
        image = apply_orientation(image, raw_orientation)
    return image


def preview_bytes_from_data(data: bytes, *, suffix: str = "") -> bytes | None:
    if suffix.lower() in RAW_SUFFIXES:
        return extract_embedded_jpeg(data)
    if qimage_from_bytes(data) is not None:
        return data
    return None


def load_preview_image(source_path: Path) -> QImage:
    suffix = source_path.suffix.lower()
    if suffix in RAW_SUFFIXES and source_path.exists():
        try:
            image = preview_image_from_data(source_path.read_bytes(), suffix=suffix)
        except Exception:
            image = None
        if image is not None and not image.isNull():
            return image

    reader = QImageReader(str(source_path))
    reader.setAutoTransform(True)
    image = reader.read()
    if not image.isNull():
        return image

    return placeholder_image(QSize(220, 160), label=source_path.suffix.upper().lstrip(".") or "FILE")


def build_thumbnail(source_path: Path, thumb_path: Path, size: QSize = QSize(220, 160)) -> Path:
    image = load_preview_image(source_path)
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


def _extract_jpeg_orientation(data: bytes) -> int | None:
    if len(data) < 4 or not data.startswith(_JPEG_SOI):
        return None

    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue

        marker = data[offset + 1]
        if marker in {0xD8, 0xD9}:
            offset += 2
            continue

        segment_length = int.from_bytes(data[offset + 2 : offset + 4], "big")
        if segment_length < 2:
            return None
        segment_end = offset + 2 + segment_length
        if segment_end > len(data):
            return None

        if marker == 0xE1 and data[offset + 4 : offset + 10] == _JPEG_EXIF_MARKER:
            return _extract_tiff_orientation(data, offset + 10)
        offset = segment_end
    return None


def _extract_jpeg_sample_precision(data: bytes) -> int | None:
    if len(data) < 4 or not data.startswith(_JPEG_SOI):
        return None

    offset = 2
    while offset + 1 < len(data):
        while offset < len(data) and data[offset] != 0xFF:
            offset += 1
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break

        marker = data[offset]
        offset += 1

        if marker == 0xD9:
            break
        if marker in {0x01, *range(0xD0, 0xD9)}:
            continue
        if offset + 2 > len(data):
            break

        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            break
        if marker in _JPEG_SOF_MARKERS:
            if segment_length < 7 or offset + 2 >= len(data):
                break
            return int(data[offset + 2])
        offset += segment_length
    return None


def _extract_tiff_orientation(data: bytes, offset: int) -> int | None:
    if len(data) < offset + 8:
        return None

    byte_order = data[offset : offset + 2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return None

    if struct.unpack_from(f"{endian}H", data, offset + 2)[0] != 42:
        return None

    ifd0_offset = struct.unpack_from(f"{endian}I", data, offset + 4)[0]
    directory_offset = offset + ifd0_offset
    if len(data) < directory_offset + 2:
        return None

    entry_count = struct.unpack_from(f"{endian}H", data, directory_offset)[0]
    for index in range(entry_count):
        entry_offset = directory_offset + 2 + (index * 12)
        if len(data) < entry_offset + 12:
            break
        tag, value_type, value_count, value_or_offset = struct.unpack_from(f"{endian}HHII", data, entry_offset)
        if tag != _EXIF_ORIENTATION_TAG or value_count < 1:
            continue
        if value_type == 3:
            return value_or_offset & 0xFFFF if endian == "<" else value_or_offset >> 16
        if value_type == 4:
            return int(value_or_offset)
    return None
