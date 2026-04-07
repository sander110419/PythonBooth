from __future__ import annotations

from pathlib import Path

from .image_utils import SUPPORTED_IMPORT_SUFFIXES


class HotFolderWatcher:
    def __init__(self) -> None:
        self._folder: Path | None = None
        self._seen: set[Path] = set()
        self._pending: dict[Path, tuple[int, float, int]] = {}

    def set_folder(self, folder: str | Path | None) -> None:
        self._folder = Path(folder).expanduser() if folder else None
        self._seen.clear()
        self._pending.clear()

    def scan(self) -> list[Path]:
        if self._folder is None or not self._folder.exists():
            return []

        discovered: list[Path] = []
        for path in sorted(self._folder.iterdir()):
            if not path.is_file():
                continue
            if path in self._seen:
                continue
            if path.suffix.lower() not in SUPPORTED_IMPORT_SUFFIXES:
                continue

            stat = path.stat()
            current = (int(stat.st_size), float(stat.st_mtime))
            prior = self._pending.get(path)
            if prior is None:
                self._pending[path] = (current[0], current[1], 1)
                continue
            if current[0] == prior[0] and current[1] == prior[1]:
                stable_count = prior[2] + 1
                if stable_count >= 2:
                    self._seen.add(path)
                    self._pending.pop(path, None)
                    discovered.append(path)
                else:
                    self._pending[path] = (current[0], current[1], stable_count)
            else:
                self._pending[path] = (current[0], current[1], 1)
        return discovered
