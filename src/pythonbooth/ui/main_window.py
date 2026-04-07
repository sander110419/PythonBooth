from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, ConfigStore
from ..models import CapturePayload, CameraStatus
from ..services.camera_manager import CameraManager
from ..services.hot_folder import HotFolderWatcher
from ..services.library import SessionLibrary
from ..services.naming import NamingContext, compile_filename, sanitize_filename_part
from .options_dialog import OptionsDialog
from .secondary_window import SecondaryDisplayWindow
from .timeline import TimelineWidget
from .viewer import PhotoViewer

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config_store: ConfigStore, config: AppConfig):
        super().__init__()
        self.config_store = config_store
        self.config = config
        self.secondary_windows: list[SecondaryDisplayWindow] = []
        self.selected_photo_id = config.selected_photo_id or ""

        self.session_id = ""
        self.session_library = self._create_session_library(config.session_name)
        self.hot_folder = HotFolderWatcher()
        self.hot_folder.set_folder(config.hot_folder_path if config.hot_folder_enabled else None)

        self.camera_manager = CameraManager(
            backend_name=config.backend,
            auto_reconnect=config.auto_reconnect,
            simulator_auto_capture_seconds=config.simulator_auto_capture_seconds,
            edsdk_path=config.edsdk_path,
        )

        self.setWindowTitle("PythonBooth")
        self.resize(1720, 1040)
        self.setMinimumSize(1360, 860)
        self._build_ui()
        self.selected_viewer.set_zoom_enabled(self.config.zoom_enabled)
        self._bind_shortcuts()
        self._bind_signals()
        self._refresh_timeline()
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()
        self._apply_status(CameraStatus.idle(self.config.backend, f"{self.config.backend.title()} ready"))

        self.hot_folder_timer = QTimer(self)
        self.hot_folder_timer.setInterval(1200)
        self.hot_folder_timer.timeout.connect(self._scan_hot_folder)
        self.hot_folder_timer.start()

        self.camera_manager.start()
        self.camera_manager.switch_backend(self.config.backend)

    def closeEvent(self, event) -> None:
        self._persist_config()
        self.camera_manager.stop()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(16)

        outer.addWidget(self._build_top_bar())
        outer.addWidget(self._build_content(), 1)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_message("Ready")

    def _build_top_bar(self) -> QWidget:
        card = self._card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(4)

        title = QLabel("PythonBooth")
        title.setObjectName("TitleLabel")
        self.session_path_label = QLabel("")
        self.session_path_label.setObjectName("MutedText")
        self.session_path_label.setWordWrap(True)
        self.camera_info_label = QLabel("Waiting for camera")
        self.camera_info_label.setObjectName("MutedText")
        self.camera_info_label.setWordWrap(True)

        left.addWidget(title)
        left.addWidget(self.session_path_label)
        left.addWidget(self.camera_info_label)
        layout.addLayout(left, 1)

        self.reconnect_button = QPushButton("Reconnect")
        self.capture_button = QPushButton("Capture")
        self.capture_button.setProperty("accent", "true")
        self.new_session_button = QPushButton("New Session")
        self.new_display_button = QPushButton("Secondary Window")

        self.options_button = QToolButton()
        self.options_button.setText("Options")
        self.options_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.options_menu = QMenu(self.options_button)
        self.options_action = QAction("Booth Options", self)
        self.open_folder_action = QAction("Open Session Folder", self)
        self.options_menu.addAction(self.options_action)
        self.options_menu.addAction(self.open_folder_action)
        self.options_button.setMenu(self.options_menu)

        self.status_pill = QLabel("Idle")
        self.status_pill.setObjectName("StatusPill")
        self.status_pill.setProperty("statusState", "idle")
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.reconnect_button)
        actions.addWidget(self.capture_button)
        actions.addWidget(self.new_session_button)
        actions.addWidget(self.new_display_button)
        actions.addWidget(self.options_button)
        actions.addWidget(self.status_pill)
        layout.addLayout(actions, 0)
        return card

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_preview_card(), 1)

        timeline_card = self._build_timeline_card()
        timeline_card.setMinimumHeight(220)
        timeline_card.setMaximumHeight(300)
        layout.addWidget(timeline_card, 0)
        return content

    def _build_preview_card(self) -> QWidget:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(14)

        header_left = QVBoxLayout()
        header_left.setSpacing(4)
        section = self._section_title("Preview")
        self.next_filename_label = QLabel("")
        self.next_filename_label.setObjectName("MutedText")
        self.next_filename_label.setWordWrap(True)
        header_left.addWidget(section)
        header_left.addWidget(self.next_filename_label)
        header.addLayout(header_left, 1)
        header.addWidget(self._build_preview_toolbar(), 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.selected_viewer = PhotoViewer()
        self.selected_viewer.setMinimumHeight(620)
        layout.addWidget(self.selected_viewer, 1)

        footer = QHBoxLayout()
        footer.setSpacing(18)
        self.session_stats_label = QLabel("")
        self.session_stats_label.setObjectName("MutedText")
        self.session_stats_label.setWordWrap(True)
        self.selected_meta_label = QLabel("No photo selected")
        self.selected_meta_label.setObjectName("MutedText")
        self.selected_meta_label.setWordWrap(True)
        self.selected_meta_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        footer.addWidget(self.session_stats_label, 1)
        footer.addWidget(self.selected_meta_label, 1)
        layout.addLayout(footer)

        return card

    def _build_preview_toolbar(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.zoom_toggle = QPushButton("Zoom")
        self.zoom_toggle.setCheckable(True)
        self.zoom_toggle.setChecked(self.config.zoom_enabled)
        self.zoom_in_button = QPushButton("+")
        self.zoom_out_button = QPushButton("-")
        self.zoom_reset_button = QPushButton("Reset")
        self.fit_button = QPushButton("Fit")
        self.fill_button = QPushButton("Fill")
        self.delete_button = QPushButton("Delete")

        layout.addWidget(self.zoom_toggle)
        layout.addWidget(self.zoom_in_button)
        layout.addWidget(self.zoom_out_button)
        layout.addWidget(self.zoom_reset_button)
        layout.addWidget(self.fit_button)
        layout.addWidget(self.fill_button)
        layout.addWidget(self.delete_button)
        return row

    def _build_timeline_card(self) -> QWidget:
        card = self._card("TimelineCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title_row.addWidget(self._section_title("Timeline"))
        self.timeline_hint_label = QLabel("Newest capture is selected automatically. Right-click a thumbnail to delete.")
        self.timeline_hint_label.setObjectName("MutedText")
        self.timeline_hint_label.setWordWrap(True)
        title_row.addWidget(self.timeline_hint_label, 1)
        layout.addLayout(title_row)

        self.timeline = TimelineWidget()
        layout.addWidget(self.timeline, 1)
        return card

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence("Space"), self, activated=self.camera_manager.request_capture)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._create_secondary_window)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_selected_photo)
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, activated=self._start_new_session)

    def _bind_signals(self) -> None:
        self.camera_manager.status_updated.connect(self._apply_status)
        self.camera_manager.capture_ready.connect(self._on_capture_ready)

        self.reconnect_button.clicked.connect(self.camera_manager.request_reconnect)
        self.capture_button.clicked.connect(self.camera_manager.request_capture)
        self.new_session_button.clicked.connect(self._start_new_session)
        self.new_display_button.clicked.connect(self._create_secondary_window)
        self.options_action.triggered.connect(self._open_options_dialog)
        self.open_folder_action.triggered.connect(self._open_session_folder)

        self.zoom_toggle.toggled.connect(self.selected_viewer.set_zoom_enabled)
        self.zoom_in_button.clicked.connect(self.selected_viewer.zoom_in)
        self.zoom_out_button.clicked.connect(self.selected_viewer.zoom_out)
        self.zoom_reset_button.clicked.connect(self.selected_viewer.reset_zoom)
        self.fit_button.clicked.connect(lambda: self.selected_viewer.set_display_mode("fit"))
        self.fill_button.clicked.connect(lambda: self.selected_viewer.set_display_mode("fill"))
        self.delete_button.clicked.connect(self._delete_selected_photo)

        self.timeline.photo_selected.connect(self._select_photo)
        self.timeline.delete_requested.connect(self._delete_photo_by_id)

    def _apply_status(self, status: CameraStatus) -> None:
        self.camera_info_label.setText(status.message if not status.last_error else f"{status.message} | {status.last_error}")
        self.status_pill.setText(status.state.title())
        self.status_pill.setProperty("statusState", status.state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.status_message(status.message)

    def _open_options_dialog(self) -> None:
        dialog = OptionsDialog(self, config=self.config)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        updated = dialog.options_dict()
        previous_backend = self.config.backend
        previous_session_name = self.config.session_name

        self.config.backend = str(updated.get("backend") or self.config.backend)
        self.config.event_name = str(updated.get("event_name", self.config.event_name))
        self.config.booth_name = str(updated.get("booth_name", self.config.booth_name))
        self.config.session_name = str(updated.get("session_name", self.config.session_name))
        self.config.naming_template = str(updated.get("naming_template", self.config.naming_template))
        self.config.auto_reconnect = bool(updated.get("auto_reconnect", self.config.auto_reconnect))
        self.config.hot_folder_enabled = bool(updated.get("hot_folder_enabled", self.config.hot_folder_enabled))
        self.config.hot_folder_path = str(updated.get("hot_folder_path", self.config.hot_folder_path))
        self.config.simulator_auto_capture_seconds = float(
            updated.get("simulator_auto_capture_seconds", self.config.simulator_auto_capture_seconds)
        )
        self.config.edsdk_path = str(updated.get("edsdk_path", self.config.edsdk_path))

        self.hot_folder.set_folder(self.config.hot_folder_path if self.config.hot_folder_enabled else None)
        self.camera_manager.update_runtime_options(
            auto_reconnect=self.config.auto_reconnect,
            simulator_auto_capture_seconds=self.config.simulator_auto_capture_seconds,
            edsdk_path=self.config.edsdk_path,
        )
        if previous_backend != self.config.backend:
            self.camera_manager.switch_backend(self.config.backend)

        self._update_filename_preview()
        self._update_session_labels()
        self._persist_config()

        if previous_session_name != self.config.session_name:
            if not self.session_library.records:
                self._start_new_session()
            else:
                self.status_message("Options saved. Start a new session to apply the new series name.")
        else:
            self.status_message("Options saved.")

    def _on_capture_ready(self, capture: CapturePayload) -> None:
        record = self.session_library.add_capture(capture, self._build_filename)
        self.selected_photo_id = record.id
        self._refresh_timeline(record.id)
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()
        self.status_message(f"Imported {record.display_name}")

    def _build_filename(self, capture: CapturePayload, session_sequence: int) -> str:
        template = self.config.naming_template.strip() or "{EVENT}_{BOOTH}_{DAY}_{CAMERA:05d}.{EXT}"
        extension = Path(capture.original_filename).suffix.lstrip(".") or "jpg"
        context = NamingContext(
            event_name=self.config.event_name.strip(),
            booth_name=self.config.booth_name.strip(),
            machine_name=self.config.booth_name,
            session_name=self.config.session_name.strip(),
            session_id=self.session_id,
            capture_datetime=capture.captured_at,
            camera_sequence=capture.camera_sequence or session_sequence,
            session_sequence=session_sequence,
            extension=extension,
            preferred_sequence_source="camera" if capture.camera_sequence else "session",
        )
        return compile_filename(template, context).filename

    def _refresh_timeline(self, selected_id: str | None = None) -> None:
        selected_id = selected_id or self.selected_photo_id
        records = self.session_library.records
        self.timeline.set_records(records, selected_id=selected_id)
        if records and not selected_id:
            self.selected_photo_id = records[-1].id

    def _select_photo(self, photo_id: str) -> None:
        self.selected_photo_id = photo_id
        self._update_selected_preview()
        self._update_filename_preview()
        self._persist_config()

    def _update_selected_preview(self) -> None:
        if not self.selected_photo_id:
            self.selected_viewer.set_image(QImage())
            self._update_secondary_windows(image=QImage(), title="Secondary Display")
            self.selected_meta_label.setText("No captured image selected")
            return

        record = self.session_library.get(self.selected_photo_id)
        if record is None:
            self.selected_photo_id = ""
            self._update_selected_preview()
            return

        image_path = record.preview or record.path
        image = QImage(str(image_path))
        self.selected_viewer.set_image(image)
        self.selected_meta_label.setText(
            f"{record.display_name}\nCaptured {record.captured_at}\nSource {record.source}\nOriginal {record.original_filename}"
        )
        self._update_secondary_windows(image=image, title=record.display_name)

    def _update_secondary_windows(self, image: QImage | None = None, title: str = "Secondary Display") -> None:
        if image is None and self.selected_photo_id:
            record = self.session_library.get(self.selected_photo_id)
            if record is not None:
                image_path = record.preview or record.path
                image = QImage(str(image_path))
                title = record.display_name

        for window in list(self.secondary_windows):
            if window.isVisible():
                window.set_image(image, title=title)
            else:
                self.secondary_windows.remove(window)

    def _update_filename_preview(self) -> None:
        template = self.config.naming_template.strip() or "{EVENT}_{BOOTH}_{DAY}_{CAMERA:05d}.{EXT}"
        next_session_sequence = self.session_library.next_session_sequence()
        last_camera_sequence = 0
        for record in self.session_library.records:
            if record.camera_sequence:
                last_camera_sequence = max(last_camera_sequence, int(record.camera_sequence))
        context = NamingContext(
            event_name=self.config.event_name.strip(),
            booth_name=self.config.booth_name.strip(),
            machine_name=self.config.booth_name,
            session_name=self.config.session_name.strip(),
            session_id=self.session_id,
            capture_datetime=datetime.now(),
            camera_sequence=last_camera_sequence + 1,
            session_sequence=next_session_sequence,
            extension="jpg",
        )
        compiled = compile_filename(template, context)
        self.next_filename_label.setText(f"Next filename: {compiled.filename}")

    def _update_session_labels(self) -> None:
        count = len(self.session_library.records)
        series_name = self.config.session_name.strip() or "Untitled"
        self.session_stats_label.setText(
            f"{count} photo{'s' if count != 1 else ''}\nCurrent session: {self.session_id}\nFolder: {self.session_library.session_root}"
        )
        self.session_path_label.setText(
            f"Series preset: {series_name} | Current session: {self.session_id}"
        )

    def _start_new_session(self) -> None:
        self.session_library = self._create_session_library(self.config.session_name.strip() or "Session")
        self.selected_photo_id = ""
        self._refresh_timeline()
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()
        self.status_message(f"Started new session {self.session_id}")

    def _create_session_library(self, session_name: str) -> SessionLibrary:
        stem = sanitize_filename_part(session_name or "Session")
        self.session_id = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_root = self.config.resolved_output_root() / self.session_id
        session_root.mkdir(parents=True, exist_ok=True)
        return SessionLibrary(session_root)

    def _create_secondary_window(self) -> None:
        window = SecondaryDisplayWindow(self)
        self.secondary_windows.append(window)
        self._update_secondary_windows()
        window.show()

    def _delete_selected_photo(self) -> None:
        if not self.selected_photo_id:
            return
        self._delete_photo_by_id(self.selected_photo_id)

    def _delete_photo_by_id(self, photo_id: str) -> None:
        record = self.session_library.get(photo_id)
        if record is None:
            return
        answer = QMessageBox.question(self, "Delete Photo", f"Delete {record.display_name} from the session?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.session_library.delete_photo(photo_id)
        self.selected_photo_id = self.session_library.records[-1].id if self.session_library.records else ""
        self._refresh_timeline(self.selected_photo_id or None)
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()

    def _open_session_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session_library.session_root)))

    def _scan_hot_folder(self) -> None:
        if not self.config.hot_folder_enabled:
            return
        imported = self.hot_folder.scan()
        for path in imported:
            try:
                record = self.session_library.import_existing_file(path, self._build_filename)
            except Exception:
                logger.exception("Failed to import hot-folder file %s", path)
                continue
            self.selected_photo_id = record.id
            self._refresh_timeline(record.id)
            self._update_selected_preview()
            self._update_filename_preview()
            self._update_session_labels()
            self.status_message(f"Imported hot-folder image {record.display_name}")

    def _persist_config(self) -> None:
        self.config.selected_photo_id = self.selected_photo_id
        self.config.zoom_enabled = self.zoom_toggle.isChecked()
        self.config_store.save(self.config)

    def status_message(self, message: str) -> None:
        if self.statusBar():
            self.statusBar().showMessage(message, 5000)

    @staticmethod
    def _card(object_name: str = "Card") -> QFrame:
        frame = QFrame()
        frame.setObjectName(object_name)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        return frame

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label
