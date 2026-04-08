from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QWidget

from .styles import normalize_background_color


class PhotoViewer(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setScene(QGraphicsScene(self))
        self._pixmap_item = QGraphicsPixmapItem()
        self.scene().addItem(self._pixmap_item)
        self.scene().setSceneRect(QRectF())
        self._background_color = QColor(normalize_background_color(None))
        self.setBackgroundBrush(self._background_color)
        self.setFrameShape(self.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._image = QImage()
        self._zoom_enabled = False
        self._display_mode = "fit"
        self._manual_zoom = 1.0

    def set_background_color(self, color: str | QColor | None) -> None:
        if isinstance(color, QColor):
            resolved = color if color.isValid() else QColor(normalize_background_color(None))
        else:
            resolved = QColor(normalize_background_color(color))
        self._background_color = resolved
        self.setBackgroundBrush(resolved)
        self.viewport().update()

    def set_image(self, image: QImage | None) -> None:
        if image is None or image.isNull():
            self._image = QImage()
            self._pixmap_item.setPixmap(QPixmap())
            self.scene().setSceneRect(QRectF())
            return
        self._image = image
        self._pixmap_item.setPixmap(QPixmap.fromImage(image))
        self.scene().setSceneRect(QRectF(self._pixmap_item.boundingRect()))
        self._apply_view_mode()

    def set_zoom_enabled(self, enabled: bool) -> None:
        self._zoom_enabled = bool(enabled)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if self._zoom_enabled else QGraphicsView.DragMode.NoDrag)
        if not self._zoom_enabled:
            self._manual_zoom = 1.0
            self._apply_view_mode()

    def zoom_in(self) -> None:
        self._apply_manual_scale(1.2)

    def zoom_out(self) -> None:
        self._apply_manual_scale(1 / 1.2)

    def reset_zoom(self) -> None:
        self._manual_zoom = 1.0
        self._apply_view_mode()

    def set_display_mode(self, mode: str) -> None:
        self._display_mode = mode
        self._apply_view_mode()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self._zoom_enabled or self._image.isNull():
            return super().wheelEvent(event)
        delta = event.angleDelta().y()
        self._apply_manual_scale(1.15 if delta > 0 else 1 / 1.15)
        event.accept()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_view_mode()

    def _apply_manual_scale(self, factor: float) -> None:
        if self._image.isNull():
            return
        self._manual_zoom = max(0.2, min(8.0, self._manual_zoom * factor))
        self.resetTransform()
        self.scale(self._manual_zoom, self._manual_zoom)

    def _apply_view_mode(self) -> None:
        if self._image.isNull():
            return
        if self._zoom_enabled:
            self.resetTransform()
            self.scale(self._manual_zoom, self._manual_zoom)
            return
        self.resetTransform()
        item_rect = self._pixmap_item.boundingRect()
        if item_rect.isEmpty():
            return
        view_rect = self.viewport().rect()
        if view_rect.isEmpty():
            return
        scale_x = view_rect.width() / item_rect.width()
        scale_y = view_rect.height() / item_rect.height()
        scale = min(scale_x, scale_y) if self._display_mode == "fit" else max(scale_x, scale_y)
        self.scale(scale, scale)
        self.centerOn(self._pixmap_item)


class AspectRatioPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewer = PhotoViewer(self)
        self._aspect_ratio = 3.0 / 2.0
        self.setMinimumHeight(520)
        self._background_color = QColor(normalize_background_color(None))
        self._apply_background_color()

    def set_image(self, image: QImage | None) -> None:
        if image is not None and not image.isNull():
            self._aspect_ratio = 2.0 / 3.0 if image.height() > image.width() else 3.0 / 2.0
        self.viewer.set_image(image)
        self._layout_viewer()

    def set_background_color(self, color: str | QColor | None) -> None:
        if isinstance(color, QColor):
            self._background_color = color if color.isValid() else QColor(normalize_background_color(None))
        else:
            self._background_color = QColor(normalize_background_color(color))
        self.viewer.set_background_color(self._background_color)
        self._apply_background_color()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_viewer()

    def _apply_background_color(self) -> None:
        color = self._background_color.name()
        self.setStyleSheet(f"background: {color}; border-radius: 18px;")

    def _layout_viewer(self) -> None:
        rect = self.contentsRect()
        if rect.isEmpty():
            self.viewer.setGeometry(rect)
            return

        ratio = max(0.1, float(self._aspect_ratio))
        available_width = rect.width()
        available_height = rect.height()

        if available_width / max(1, available_height) > ratio:
            viewer_height = available_height
            viewer_width = int(round(viewer_height * ratio))
        else:
            viewer_width = available_width
            viewer_height = int(round(viewer_width / ratio))

        viewer_rect = QRect(
            rect.x() + max(0, (available_width - viewer_width) // 2),
            rect.y() + max(0, (available_height - viewer_height) // 2),
            max(1, viewer_width),
            max(1, viewer_height),
        )
        self.viewer.setGeometry(viewer_rect)
