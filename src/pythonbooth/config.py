from __future__ import annotations

import json
import socket
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import config_dir, default_session_root, ensure_app_dirs
from .services.atomic_io import atomic_write_json


@dataclass(slots=True)
class AppConfig:
    backend: str = "simulator"
    background_color: str = "#0b1017"
    event_name: str = "Event"
    booth_name: str = socket.gethostname().upper()
    session_name: str = "Session"
    naming_template: str = "{EVENT}_{BOOTH}_{DAY}_{CAMERA:05d}.{EXT}"
    output_root: str = ""
    hot_folder_enabled: bool = False
    hot_folder_path: str = ""
    auto_reconnect: bool = True
    simulator_auto_capture_seconds: float = 0.0
    edsdk_path: str = ""
    backup_roots: list[str] = field(default_factory=list)
    verify_backup_writes: bool = True
    last_session_root: str = ""
    last_session_id: str = ""
    restore_last_session: bool = True
    secondary_windows: list[dict[str, object]] = field(default_factory=list)
    selected_photo_id: str = ""
    zoom_enabled: bool = False

    def resolved_output_root(self) -> Path:
        if self.output_root:
            return Path(self.output_root).expanduser()
        return default_session_root()


class ConfigStore:
    def __init__(self, path: Path | None = None):
        ensure_app_dirs()
        self.path = path or (config_dir() / "config.json")

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        valid = {field.name for field in AppConfig.__dataclass_fields__.values()}
        filtered = {key: value for key, value in payload.items() if key in valid}
        return AppConfig(**filtered)

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, asdict(config), indent=2)
