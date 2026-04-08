from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import QMainWindow

from .viewer import PhotoViewer


class SecondaryDisplayWindow(QMainWindow):
    def __init__(self, parent=None, *, background_color: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Secondary Display")
        self.viewer = PhotoViewer()
        self.viewer.set_display_mode("fit")
        self.viewer.set_background_color(background_color)
        self.setCentralWidget(self.viewer)
        self.resize(900, 600)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._exit_fullscreen)

    def set_background_color(self, color: str | None) -> None:
        self.viewer.set_background_color(color)

    def set_image(self, image: QImage | None, title: str = "Secondary Display") -> None:
        self.setWindowTitle(title)
        self.viewer.set_image(image)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _exit_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
