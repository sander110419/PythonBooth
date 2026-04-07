from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "PythonBooth"
APP_AUTHOR = "PythonBooth"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def default_session_root() -> Path:
    pictures_dir = Path.home() / "Pictures"
    if pictures_dir.exists():
        return pictures_dir / APP_NAME / "Sessions"
    return data_dir() / "sessions"


def ensure_app_dirs() -> dict[str, Path]:
    roots = {
        "config": config_dir(),
        "data": data_dir(),
        "sessions": default_session_root(),
    }
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
    return roots
