from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QMenu

from ..models import PhotoRecord


class TimelineWidget(QListWidget):
    photo_selected = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWrapping(False)
        self.setSpacing(12)
        self.setIconSize(QSize(160, 114))
        self.setGridSize(QSize(182, 156))
        self.itemSelectionChanged.connect(self._emit_selection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def set_records(self, records: list[PhotoRecord], selected_id: str | None = None) -> None:
        self.clear()
        to_select: QListWidgetItem | None = None
        for record in records:
            item = QListWidgetItem(record.display_name)
            item.setData(Qt.ItemDataRole.UserRole, record.id)
            thumb_path = record.thumbnail or record.preview or record.path
            pixmap = QPixmap(str(thumb_path)) if thumb_path else QPixmap()
            item.setIcon(QIcon(pixmap))
            item.setToolTip(str(record.path))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.addItem(item)
            if selected_id and record.id == selected_id:
                to_select = item
        if to_select is not None:
            self.setCurrentItem(to_select)
        elif self.count():
            self.setCurrentRow(self.count() - 1)

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is None:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("Delete Photo")
        chosen = menu.exec(event.globalPos())
        if chosen == delete_action:
            photo_id = item.data(Qt.ItemDataRole.UserRole)
            if photo_id:
                self.delete_requested.emit(str(photo_id))

    def _emit_selection(self) -> None:
        item = self.currentItem()
        if item is None:
            return
        photo_id = item.data(Qt.ItemDataRole.UserRole)
        if photo_id:
            self.photo_selected.emit(str(photo_id))
