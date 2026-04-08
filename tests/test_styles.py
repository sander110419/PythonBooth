from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from pythonbooth.ui.styles import apply_theme, build_app_stylesheet, normalize_background_color


def _app() -> QApplication:
    app = QApplication.instance()
    return app if app is not None else QApplication([])


def test_normalize_background_color_falls_back_for_invalid_input():
    assert normalize_background_color("#112233") == "#112233"
    assert normalize_background_color("not-a-color") == "#0b1017"


def test_apply_theme_keeps_default_app_shell():
    app = _app()

    apply_theme(app, "#123456")

    assert app.palette().window().color().name() == "#0b1017"
    assert app.palette().button().color().name() == "#101927"
    assert "#123456" not in app.styleSheet()
    assert "QWidget#AppRoot" in app.styleSheet()
    assert "QWidget {\n    color: #edf2ff;" in app.styleSheet()
    assert "#0b1017" in build_app_stylesheet("#123456")
