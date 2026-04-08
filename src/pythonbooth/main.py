from __future__ import annotations

import argparse
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from .config import ConfigStore
from .paths import ensure_app_dirs
from .services.logging_setup import configure_logging
from .ui.main_window import MainWindow
from .ui.styles import apply_theme


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PythonBooth photobooth manager")
    parser.add_argument("--demo", action="store_true", help="Start in simulator mode")
    parser.add_argument("--auto-exit-ms", type=int, default=0, help="Exit automatically after the given number of milliseconds")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    ensure_app_dirs()
    configure_logging(verbose=args.verbose)

    config_store = ConfigStore()
    config = config_store.load()
    if args.demo:
        config.backend = "simulator"

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    apply_theme(app)

    window = MainWindow(config_store, config)
    window.show()

    if args.auto_exit_ms > 0:
        QTimer.singleShot(args.auto_exit_ms, app.quit)

    return app.exec()
