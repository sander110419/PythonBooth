from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from ..paths import data_dir, ensure_app_dirs


def configure_logging(verbose: bool = False) -> None:
    ensure_app_dirs()
    log_root = data_dir() / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / "pythonbooth.log"

    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)
