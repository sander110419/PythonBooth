from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..models import CapturePayload, PhotoRecord, new_photo_id
from .image_utils import build_thumbnail, save_bytes, suffix_from_filename


FilenameBuilder = Callable[[CapturePayload, int], str]


class SessionLibrary:
    def __init__(self, session_root: Path):
        self.session_root = session_root
        self.images_dir = session_root / "images"
        self.previews_dir = session_root / "previews"
        self.thumbs_dir = session_root / "thumbs"
        self.index_path = session_root / "session.json"
        self.session_root.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.previews_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        self._records = self._load()

    @property
    def records(self) -> list[PhotoRecord]:
        return list(self._records)

    def _load(self) -> list[PhotoRecord]:
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

    def save(self) -> None:
        payload = {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "photos": [asdict(record) for record in self._records],
        }
        self.index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def next_session_sequence(self) -> int:
        return max((record.session_sequence for record in self._records), default=0) + 1

    def add_capture(self, capture: CapturePayload, filename_builder: FilenameBuilder) -> PhotoRecord:
        session_sequence = self.next_session_sequence()
        requested_name = filename_builder(capture, session_sequence).strip()
        suffix = Path(requested_name).suffix.lower() or suffix_from_filename(capture.original_filename)
        final_name = self._unique_name(Path(requested_name).stem or f"capture_{session_sequence:05d}", suffix)
        final_path = self.images_dir / final_name
        save_bytes(final_path, capture.data)

        preview_path = self._store_preview(final_name, final_path, capture)
        thumb_path = self.thumbs_dir / f"{Path(final_name).stem}.jpg"
        build_thumbnail(preview_path or final_path, thumb_path)

        record = PhotoRecord(
            id=new_photo_id(),
            display_name=final_name,
            file_path=str(final_path),
            preview_path=str(preview_path) if preview_path else None,
            thumbnail_path=str(thumb_path),
            captured_at=capture.captured_at.isoformat(timespec="seconds"),
            source=capture.source,
            original_filename=capture.original_filename,
            camera_sequence=capture.camera_sequence,
            session_sequence=session_sequence,
            metadata=dict(capture.metadata),
        )
        self._records.append(record)
        self.save()
        return record

    def import_existing_file(self, path: Path, filename_builder: FilenameBuilder | None = None) -> PhotoRecord:
        suffix = path.suffix.lower()
        session_sequence = self.next_session_sequence()
        if filename_builder:
            payload = CapturePayload(
                data=path.read_bytes(),
                original_filename=path.name,
                source="hot-folder",
                captured_at=datetime.fromtimestamp(path.stat().st_mtime),
            )
            requested_name = filename_builder(payload, session_sequence)
        else:
            requested_name = path.name
            payload = CapturePayload(
                data=path.read_bytes(),
                original_filename=path.name,
                source="hot-folder",
                captured_at=datetime.fromtimestamp(path.stat().st_mtime),
            )
        requested = Path(requested_name)
        final_name = self._unique_name(requested.stem or path.stem, requested.suffix or suffix)
        payload.original_filename = path.name
        return self.add_capture(payload, lambda _capture, _seq: final_name)

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
            self.save()
            return True
        return False

    def get(self, photo_id: str) -> PhotoRecord | None:
        return next((record for record in self._records if record.id == photo_id), None)

    def _unique_name(self, stem: str, suffix: str) -> str:
        candidate = f"{stem}{suffix}"
        index = 1
        while (self.images_dir / candidate).exists():
            candidate = f"{stem}_{index:02d}{suffix}"
            index += 1
        return candidate

    def _store_preview(self, final_name: str, final_path: Path, capture: CapturePayload) -> Path | None:
        preview_data = capture.preview_data
        if preview_data is None:
            return None
        preview_name = f"{Path(final_name).stem}_preview.jpg"
        preview_path = self.previews_dir / preview_name
        save_bytes(preview_path, preview_data)
        if preview_path.resolve() == final_path.resolve():
            return None
        return preview_path
