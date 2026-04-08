from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QFileDialog,
    QPushButton,
    QStatusBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig, ConfigStore
from ..models import CapturePayload, CameraStatus
from ..services.camera_manager import CameraManager
from ..services.capture_pipeline import CapturePipeline
from ..services.diagnostics import export_diagnostics_bundle
from ..services.hot_folder import HotFolderWatcher
from ..services.image_utils import load_preview_image
from ..services.library import SessionLibrary
from ..services.naming import NamingContext, compile_filename, sanitize_filename_part
from ..services.preflight import run_preflight
from .options_dialog import OptionsDialog
from .secondary_window import SecondaryDisplayWindow
from .styles import apply_theme
from .timeline import TimelineWidget
from .viewer import AspectRatioPreviewWidget

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, config_store: ConfigStore, config: AppConfig):
        super().__init__()
        self.config_store = config_store
        self.config = config
        self.secondary_windows: list[SecondaryDisplayWindow] = []
        self.selected_photo_id = config.selected_photo_id or ""
        self.last_camera_status = CameraStatus.idle(config.backend, f"{config.backend.title()} ready")
        self.last_preflight_report = None
        self._restored_previous_session = False

        self.session_id = ""
        self.session_library = self._open_or_create_session_library()
        self.capture_pipeline = self._create_capture_pipeline()
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
        self._apply_background_theme()
        self.selected_viewer.set_zoom_enabled(self.config.zoom_enabled)
        self._bind_shortcuts()
        self._bind_signals()
        recovered_records = self.capture_pipeline.recover_pending_jobs(self._build_filename)
        if recovered_records:
            self.selected_photo_id = recovered_records[-1].id
        elif self.session_library.state.selected_photo_id:
            self.selected_photo_id = self.session_library.state.selected_photo_id
        self._refresh_timeline()
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()
        self._apply_status(CameraStatus.idle(self.config.backend, f"{self.config.backend.title()} ready"))
        self._run_preflight(show_dialog=False)
        self._persist_config()

        self.hot_folder_timer = QTimer(self)
        self.hot_folder_timer.setInterval(1200)
        self.hot_folder_timer.timeout.connect(self._scan_hot_folder)
        self.hot_folder_timer.start()

        self.camera_manager.start()
        self.camera_manager.switch_backend(self.config.backend)
        if self._restored_previous_session:
            self.status_message(f"Recovered previous session {self.session_id}")

    def closeEvent(self, event) -> None:
        pending_summary = self.capture_pipeline.queue_summary()
        keep_recovery_flag = pending_summary["pending"] > 0 or pending_summary["failed"] > 0
        self.session_library.mark_needs_recovery(needs_recovery=keep_recovery_flag, last_error=self.session_library.state.last_error)
        self._persist_config()
        self.camera_manager.stop()
        super().closeEvent(event)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("AppRoot")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        outer.addWidget(self._build_top_bar())
        outer.addWidget(self._build_content(), 1)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.session_stats_label = QLabel("")
        self.selected_meta_label = QLabel("No photo selected")
        self.session_stats_label.setObjectName("MutedText")
        self.selected_meta_label.setObjectName("MutedText")
        status_bar.addPermanentWidget(self.session_stats_label, 1)
        status_bar.addPermanentWidget(self.selected_meta_label, 2)
        self.status_message("Ready")

    def _build_top_bar(self) -> QWidget:
        card = self._card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(2)

        title = QLabel("PythonBooth")
        title.setObjectName("TitleLabel")
        self.session_path_label = QLabel("")
        self.session_path_label.setObjectName("MutedText")
        self.session_path_label.setWordWrap(False)
        self.camera_info_label = QLabel("Waiting for camera")
        self.camera_info_label.setObjectName("MutedText")
        self.camera_info_label.setWordWrap(False)

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
        self.preflight_action = QAction("Run Preflight", self)
        self.diagnostics_action = QAction("Export Diagnostics", self)
        self.open_folder_action = QAction("Open Session Folder", self)
        self.options_menu.addAction(self.options_action)
        self.options_menu.addAction(self.preflight_action)
        self.options_menu.addAction(self.diagnostics_action)
        self.options_menu.addSeparator()
        self.options_menu.addAction(self.open_folder_action)
        self.options_button.setMenu(self.options_menu)

        self.status_pill = QLabel("Idle")
        self.status_pill.setObjectName("StatusPill")
        self.status_pill.setProperty("statusState", "idle")
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

        actions = QHBoxLayout()
        actions.setSpacing(8)
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
        layout.setSpacing(10)

        layout.addWidget(self._build_preview_card(), 1)

        timeline_card = self._build_timeline_card()
        timeline_card.setMinimumHeight(156)
        timeline_card.setMaximumHeight(196)
        layout.addWidget(timeline_card, 0)
        return content

    def _build_preview_card(self) -> QWidget:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.next_filename_label = QLabel("")
        self.next_filename_label.setObjectName("MutedText")
        self.next_filename_label.setWordWrap(False)
        header.addWidget(self.next_filename_label, 1)
        header.addWidget(self._build_preview_toolbar(), 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.preview_stage = AspectRatioPreviewWidget()
        self.selected_viewer = self.preview_stage.viewer
        layout.addWidget(self.preview_stage, 1)

        return card

    def _build_preview_toolbar(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

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
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

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
        self.preflight_action.triggered.connect(lambda: self._run_preflight(show_dialog=True))
        self.diagnostics_action.triggered.connect(self._export_diagnostics)
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
        self.last_camera_status = status
        self.session_library.set_camera_status(status)
        self.camera_info_label.setText(status.message if not status.last_error else f"{status.message} | {status.last_error}")
        self.status_pill.setText(status.state.title())
        self.status_pill.setProperty("statusState", status.state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.capture_button.setEnabled(status.connected or self.config.backend == "simulator")
        self.status_message(status.message)

    def _open_options_dialog(self) -> None:
        dialog = OptionsDialog(self, config=self.config)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        updated = dialog.options_dict()
        previous_backend = self.config.backend
        previous_session_name = self.config.session_name

        self.config.backend = str(updated.get("backend") or self.config.backend)
        self.config.background_color = str(updated.get("background_color", self.config.background_color))
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
        self.config.backup_roots = list(updated.get("backup_roots", self.config.backup_roots))
        self.config.verify_backup_writes = bool(updated.get("verify_backup_writes", self.config.verify_backup_writes))
        self.config.restore_last_session = bool(updated.get("restore_last_session", self.config.restore_last_session))

        self.hot_folder.set_folder(self.config.hot_folder_path if self.config.hot_folder_enabled else None)
        self.camera_manager.update_runtime_options(
            auto_reconnect=self.config.auto_reconnect,
            simulator_auto_capture_seconds=self.config.simulator_auto_capture_seconds,
            edsdk_path=self.config.edsdk_path,
        )
        self.capture_pipeline.update_settings(
            backup_roots=self.config.backup_roots,
            verify_backup_writes=self.config.verify_backup_writes,
        )
        if previous_backend != self.config.backend:
            self.camera_manager.switch_backend(self.config.backend)
        app = QApplication.instance()
        if app is not None:
            apply_theme(app)
        self._apply_background_theme()

        self.session_library.update_context(self.session_id, self.config)
        self._update_filename_preview()
        self._update_session_labels()
        self._run_preflight(show_dialog=False)
        self._persist_config()

        if previous_session_name != self.config.session_name:
            if not self.session_library.records:
                self._start_new_session()
            else:
                self.status_message("Options saved. Start a new session to apply the new series name.")
        else:
            self.status_message("Options saved.")

    def _on_capture_ready(self, capture: CapturePayload) -> None:
        record = self.capture_pipeline.process_capture(capture, self._build_filename)
        self.selected_photo_id = record.id
        self.session_library.set_selected_photo(record.id)
        self._refresh_timeline(record.id)
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()
        self._persist_config()
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
        self.session_library.set_selected_photo(photo_id)
        self._update_selected_preview()
        self._update_filename_preview()
        self._persist_config()

    def _update_selected_preview(self) -> None:
        if not self.selected_photo_id:
            self.preview_stage.set_image(QImage())
            self._update_secondary_windows(image=QImage(), title="Secondary Display")
            self.selected_meta_label.setText("No photo selected")
            return

        record = self.session_library.get(self.selected_photo_id)
        if record is None:
            self.selected_photo_id = ""
            self._update_selected_preview()
            return

        image = load_preview_image(record.display_preview_source)
        self.preview_stage.set_image(image)
        self.selected_meta_label.setText(
            f"Selected: {record.display_name} | Captured {record.captured_at} | Source {record.source} | Original {record.original_filename}"
        )
        self._update_secondary_windows(image=image, title=record.display_name)

    def _update_secondary_windows(self, image: QImage | None = None, title: str = "Secondary Display") -> None:
        if image is None and self.selected_photo_id:
            image, title = self._current_secondary_window_payload()

        for window in list(self.secondary_windows):
            if window.isVisible():
                window.set_image(image, title=title)
            else:
                self.secondary_windows.remove(window)

    def _current_secondary_window_payload(self) -> tuple[QImage, str]:
        if not self.selected_photo_id:
            return QImage(), "Secondary Display"

        record = self.session_library.get(self.selected_photo_id)
        if record is None:
            return QImage(), "Secondary Display"

        return load_preview_image(record.display_preview_source), record.display_name

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
        self.next_filename_label.setText(f"Next: {compiled.filename}")

    def _update_session_labels(self) -> None:
        count = len(self.session_library.records)
        series_name = self.config.session_name.strip() or "Untitled"
        queue = self.capture_pipeline.queue_summary()
        queue_text = f"Queue {queue['pending']} pending | {queue['failed']} failed | {queue['warnings']} warnings"
        self.session_stats_label.setText(f"{count} photo{'s' if count != 1 else ''} | Session {self.session_id} | {queue_text}")
        self.session_path_label.setText(
            f"Series preset: {series_name} | Current session: {self.session_id}"
        )

    def _start_new_session(self) -> None:
        self.session_library.mark_needs_recovery(needs_recovery=False)
        self.session_library = self._create_session_library(self.config.session_name.strip() or "Session")
        self.capture_pipeline = self._create_capture_pipeline()
        self.session_library.update_context(self.session_id, self.config)
        self.session_library.mark_needs_recovery(needs_recovery=True)
        self.selected_photo_id = ""
        self.session_library.set_selected_photo("")
        self._refresh_timeline()
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()
        self._run_preflight(show_dialog=False)
        self._persist_config()
        self.status_message(f"Started new session {self.session_id}")

    def _create_session_library(self, session_name: str) -> SessionLibrary:
        stem = sanitize_filename_part(session_name or "Session")
        self.session_id = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session_root = self.config.resolved_output_root() / self.session_id
        session_root.mkdir(parents=True, exist_ok=True)
        library = SessionLibrary(session_root)
        library.update_context(self.session_id, self.config)
        library.mark_needs_recovery(needs_recovery=True)
        return library

    def _open_or_create_session_library(self) -> SessionLibrary:
        if self.config.restore_last_session and self.config.last_session_root:
            last_root = Path(self.config.last_session_root).expanduser()
            if last_root.exists():
                library = SessionLibrary(last_root)
                if library.state.needs_recovery:
                    self.session_id = library.state.session_id or last_root.name
                    self.selected_photo_id = library.state.selected_photo_id or self.selected_photo_id
                    self._restored_previous_session = True
                    library.update_context(self.session_id, self.config)
                    library.mark_needs_recovery(needs_recovery=True, last_error=library.state.last_error)
                    return library
        return self._create_session_library(self.config.session_name)

    def _create_capture_pipeline(self) -> CapturePipeline:
        return CapturePipeline(
            self.session_library,
            backup_roots=self.config.backup_roots,
            verify_backup_writes=self.config.verify_backup_writes,
        )

    def _create_secondary_window(self) -> None:
        window = SecondaryDisplayWindow(self, background_color=self.config.background_color)
        self.secondary_windows.append(window)
        image, title = self._current_secondary_window_payload()
        window.set_image(image, title=title)
        window.show()

    def _apply_background_theme(self) -> None:
        self.preview_stage.set_background_color(self.config.background_color)
        for window in list(self.secondary_windows):
            window.set_background_color(self.config.background_color)

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
        self.session_library.set_selected_photo(self.selected_photo_id)
        self._refresh_timeline(self.selected_photo_id or None)
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()
        self._persist_config()

    def _open_session_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session_library.session_root)))

    def _scan_hot_folder(self) -> None:
        if not self.config.hot_folder_enabled:
            return
        imported = self.hot_folder.scan()
        for path in imported:
            try:
                record = self.capture_pipeline.process_existing_file(path, self._build_filename)
            except Exception:
                logger.exception("Failed to import hot-folder file %s", path)
                continue
            self.selected_photo_id = record.id
            self.session_library.set_selected_photo(record.id)
            self._refresh_timeline(record.id)
            self._update_selected_preview()
            self._update_filename_preview()
            self._update_session_labels()
            self._persist_config()
            self.status_message(f"Imported hot-folder image {record.display_name}")

    def _run_preflight(self, *, show_dialog: bool) -> None:
        self.last_preflight_report = run_preflight(
            config=self.config,
            session_library=self.session_library,
            camera_status=self.last_camera_status,
        )
        if not show_dialog:
            if self.last_preflight_report.overall_status != "pass":
                self.status_message(
                    f"Preflight: {len(self.last_preflight_report.failed)} failed, {len(self.last_preflight_report.warnings)} warning(s)"
                )
            return

        lines = [f"Overall status: {self.last_preflight_report.overall_status.title()}"]
        for check in self.last_preflight_report.checks:
            detail = f"\n{check.details}" if check.details else ""
            lines.append(f"[{check.severity.upper()}] {check.name}: {check.message}{detail}")
        QMessageBox.information(self, "Preflight Report", "\n\n".join(lines))

    def _export_diagnostics(self) -> None:
        suggested = self.session_library.session_root / f"pythonbooth_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export diagnostics bundle",
            str(suggested),
            "Zip Archive (*.zip)",
        )
        if not filename:
            return
        bundle = export_diagnostics_bundle(
            Path(filename),
            config=self.config,
            session_library=self.session_library,
            camera_status=self.last_camera_status,
            preflight_report=self.last_preflight_report,
        )
        self.status_message(f"Diagnostics exported to {bundle.name}")

    def _persist_config(self) -> None:
        self.config.selected_photo_id = self.selected_photo_id
        self.config.zoom_enabled = self.zoom_toggle.isChecked()
        self.config.last_session_root = str(self.session_library.session_root)
        self.config.last_session_id = self.session_id
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
