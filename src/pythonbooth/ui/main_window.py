from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
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
        self.resize(1680, 1020)
        self.setMinimumSize(1280, 820)
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
        outer.setContentsMargins(22, 22, 22, 22)
        outer.setSpacing(18)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_controls())
        outer.addWidget(self._build_content(), 1)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_message("Ready")

    def _build_header(self) -> QWidget:
        card = self._card()
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        title_wrap = QVBoxLayout()
        title = QLabel("PythonBooth")
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Canon tethering, review timeline, and multi-display photo presentation")
        subtitle.setObjectName("MutedText")
        title_wrap.addWidget(title)
        title_wrap.addWidget(subtitle)
        layout.addLayout(title_wrap, 1)

        self.session_path_label = QLabel("")
        self.session_path_label.setObjectName("MutedText")
        self.session_path_label.setWordWrap(True)
        self.status_pill = QLabel("Idle")
        self.status_pill.setObjectName("StatusPill")
        self.status_pill.setProperty("statusState", "idle")
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

        layout.addWidget(self.session_path_label, 2)
        layout.addWidget(self.status_pill, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return card

    def _build_controls(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        layout.addWidget(self._build_connection_card(), 1)
        layout.addWidget(self._build_naming_card(), 2)
        layout.addWidget(self._build_workflow_card(), 2)
        return row

    def _build_connection_card(self) -> QWidget:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.addWidget(self._section_title("Connection"))

        self.backend_combo = QComboBox()
        for backend_id, label in CameraManager.backend_options():
            self.backend_combo.addItem(label, backend_id)
        self._set_combo_value(self.backend_combo, self.config.backend)

        self.reconnect_button = QPushButton("Connect / Reconnect")
        self.reconnect_button.setProperty("accent", "true")
        self.capture_button = QPushButton("Capture Photo")
        self.capture_button.setProperty("accent", "true")
        self.new_session_button = QPushButton("New Session")
        self.new_display_button = QPushButton("Open Secondary Window")
        self.open_folder_button = QPushButton("Open Session Folder")

        self.camera_info_label = QLabel("No camera connected")
        self.camera_info_label.setWordWrap(True)
        self.camera_info_label.setObjectName("MutedText")

        layout.addWidget(QLabel("Backend"))
        layout.addWidget(self.backend_combo)
        layout.addSpacing(8)
        layout.addWidget(self.reconnect_button)
        layout.addWidget(self.capture_button)
        layout.addWidget(self.new_session_button)
        layout.addWidget(self.new_display_button)
        layout.addWidget(self.open_folder_button)
        layout.addStretch(1)
        layout.addWidget(self.camera_info_label)
        return card

    def _build_naming_card(self) -> QWidget:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.addWidget(self._section_title("Naming & Session"))

        form = QFormLayout()
        form.setSpacing(12)

        self.event_input = QLineEdit(self.config.event_name)
        self.booth_input = QLineEdit(self.config.booth_name)
        self.session_input = QLineEdit(self.config.session_name)
        self.template_input = QLineEdit(self.config.naming_template)
        self.filename_preview_label = QLabel("")
        self.filename_preview_label.setWordWrap(True)
        self.filename_preview_label.setObjectName("MutedText")

        form.addRow("Event", self.event_input)
        form.addRow("Booth", self.booth_input)
        form.addRow("Series", self.session_input)
        form.addRow("Template", self.template_input)

        layout.addLayout(form)
        layout.addWidget(self._section_title("Next Filename"))
        layout.addWidget(self.filename_preview_label)
        layout.addStretch(1)
        return card

    def _build_workflow_card(self) -> QWidget:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.addWidget(self._section_title("Workflow"))

        form = QFormLayout()
        form.setSpacing(12)

        self.auto_reconnect_check = QCheckBox("Auto reconnect")
        self.auto_reconnect_check.setChecked(self.config.auto_reconnect)
        self.hot_folder_check = QCheckBox("Enable hot folder import")
        self.hot_folder_check.setChecked(self.config.hot_folder_enabled)
        self.hot_folder_input = QLineEdit(self.config.hot_folder_path)
        self.hot_folder_browse = QToolButton()
        self.hot_folder_browse.setText("Browse")
        self.sim_capture_spin = QDoubleSpinBox()
        self.sim_capture_spin.setRange(0.0, 60.0)
        self.sim_capture_spin.setSingleStep(0.5)
        self.sim_capture_spin.setValue(self.config.simulator_auto_capture_seconds)
        self.sim_capture_spin.setSuffix(" s")
        self.sdk_path_input = QLineEdit(self.config.edsdk_path)
        self.sdk_browse = QToolButton()
        self.sdk_browse.setText("Browse")

        hot_row = QWidget()
        hot_row_layout = QHBoxLayout(hot_row)
        hot_row_layout.setContentsMargins(0, 0, 0, 0)
        hot_row_layout.addWidget(self.hot_folder_input, 1)
        hot_row_layout.addWidget(self.hot_folder_browse)

        sdk_row = QWidget()
        sdk_row_layout = QHBoxLayout(sdk_row)
        sdk_row_layout.setContentsMargins(0, 0, 0, 0)
        sdk_row_layout.addWidget(self.sdk_path_input, 1)
        sdk_row_layout.addWidget(self.sdk_browse)

        form.addRow(self.auto_reconnect_check)
        form.addRow(self.hot_folder_check)
        form.addRow("Hot folder", hot_row)
        form.addRow("Sim auto-capture", self.sim_capture_spin)
        form.addRow("Canon SDK path", sdk_row)
        layout.addLayout(form)
        layout.addStretch(1)
        return card

    def _build_content(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._build_preview_split())
        splitter.addWidget(self._build_timeline_card())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        return splitter

    def _build_preview_split(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        selected_card = self._card()
        selected_layout = QVBoxLayout(selected_card)
        selected_layout.addWidget(self._section_title("Selected Preview"))
        selected_layout.addWidget(self._build_preview_toolbar())
        self.selected_viewer = PhotoViewer()
        self.selected_viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        selected_layout.addWidget(self.selected_viewer, 1)
        splitter.addWidget(selected_card)

        detail_card = self._card()
        detail_layout = QFormLayout(detail_card)
        detail_layout.setSpacing(10)
        self.session_stats_label = QLabel("")
        self.session_stats_label.setWordWrap(True)
        self.selected_meta_label = QLabel("No photo selected")
        self.selected_meta_label.setWordWrap(True)
        detail_layout.addRow("Session", self.session_stats_label)
        detail_layout.addRow("Selected", self.selected_meta_label)

        splitter.addWidget(detail_card)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        return splitter

    def _build_preview_toolbar(self) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.zoom_toggle = QPushButton("Toggle Zoom")
        self.zoom_toggle.setCheckable(True)
        self.zoom_toggle.setChecked(self.config.zoom_enabled)
        self.zoom_in_button = QPushButton("Zoom +")
        self.zoom_out_button = QPushButton("Zoom -")
        self.zoom_reset_button = QPushButton("Reset")
        self.fit_button = QPushButton("Fit")
        self.fill_button = QPushButton("Fill")
        self.delete_button = QPushButton("Delete Selected")

        layout.addWidget(self.zoom_toggle)
        layout.addWidget(self.zoom_in_button)
        layout.addWidget(self.zoom_out_button)
        layout.addWidget(self.zoom_reset_button)
        layout.addWidget(self.fit_button)
        layout.addWidget(self.fill_button)
        layout.addStretch(1)
        layout.addWidget(self.delete_button)
        return row

    def _build_timeline_card(self) -> QWidget:
        card = self._card("TimelineCard")
        layout = QVBoxLayout(card)
        layout.addWidget(self._section_title("Timeline"))
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

        self.backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        self.reconnect_button.clicked.connect(self.camera_manager.request_reconnect)
        self.capture_button.clicked.connect(self.camera_manager.request_capture)
        self.new_session_button.clicked.connect(self._start_new_session)
        self.new_display_button.clicked.connect(self._create_secondary_window)
        self.open_folder_button.clicked.connect(self._open_session_folder)

        self.zoom_toggle.toggled.connect(self.selected_viewer.set_zoom_enabled)
        self.zoom_in_button.clicked.connect(self.selected_viewer.zoom_in)
        self.zoom_out_button.clicked.connect(self.selected_viewer.zoom_out)
        self.zoom_reset_button.clicked.connect(self.selected_viewer.reset_zoom)
        self.fit_button.clicked.connect(lambda: self.selected_viewer.set_display_mode("fit"))
        self.fill_button.clicked.connect(lambda: self.selected_viewer.set_display_mode("fill"))
        self.delete_button.clicked.connect(self._delete_selected_photo)

        self.timeline.photo_selected.connect(self._select_photo)
        self.timeline.delete_requested.connect(self._delete_photo_by_id)

        for widget in (self.event_input, self.booth_input, self.session_input, self.template_input):
            widget.textChanged.connect(self._update_filename_preview)
        self.hot_folder_check.toggled.connect(self._on_hot_folder_toggled)
        self.hot_folder_browse.clicked.connect(self._browse_hot_folder)
        self.hot_folder_input.textChanged.connect(self._on_hot_folder_path_changed)
        self.sdk_browse.clicked.connect(self._browse_sdk_path)
        self.auto_reconnect_check.toggled.connect(self._push_runtime_options)
        self.sim_capture_spin.valueChanged.connect(self._push_runtime_options)
        self.sdk_path_input.textChanged.connect(self._push_runtime_options)

    def _apply_status(self, status: CameraStatus) -> None:
        self.camera_info_label.setText(status.message if not status.last_error else f"{status.message}\n{status.last_error}")
        self.status_pill.setText(status.state.title())
        self.status_pill.setProperty("statusState", status.state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)
        self.status_message(status.message)

    def _on_backend_changed(self) -> None:
        backend_name = self.backend_combo.currentData()
        self.config.backend = str(backend_name)
        self.camera_manager.switch_backend(self.config.backend)
        self._update_filename_preview()

    def _on_capture_ready(self, capture: CapturePayload) -> None:
        record = self.session_library.add_capture(capture, self._build_filename)
        self.selected_photo_id = record.id
        self._refresh_timeline(record.id)
        self._update_selected_preview()
        self._update_filename_preview()
        self._update_session_labels()
        self.status_message(f"Imported {record.display_name}")

    def _build_filename(self, capture: CapturePayload, session_sequence: int) -> str:
        template = self.template_input.text().strip() or self.config.naming_template
        extension = Path(capture.original_filename).suffix.lstrip(".") or "jpg"
        context = NamingContext(
            event_name=self.event_input.text().strip(),
            booth_name=self.booth_input.text().strip(),
            machine_name=self.config.booth_name,
            session_name=self.session_input.text().strip(),
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
            f"{record.display_name}\n{record.captured_at}\nSource: {record.source}\nOriginal: {record.original_filename}"
        )
        self._update_secondary_windows(image=image, title=record.display_name)

    def _update_secondary_windows(self, image: QImage | None = None, title: str = "Secondary Display") -> None:
        if image is None:
            if self.selected_photo_id:
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
        template = self.template_input.text().strip() or self.config.naming_template
        next_session_sequence = self.session_library.next_session_sequence()
        last_camera_sequence = 0
        for record in self.session_library.records:
            if record.camera_sequence:
                last_camera_sequence = max(last_camera_sequence, int(record.camera_sequence))
        context = NamingContext(
            event_name=self.event_input.text().strip(),
            booth_name=self.booth_input.text().strip(),
            machine_name=self.config.booth_name,
            session_name=self.session_input.text().strip(),
            session_id=self.session_id,
            capture_datetime=datetime.now(),
            camera_sequence=last_camera_sequence + 1,
            session_sequence=next_session_sequence,
            extension="jpg",
        )
        compiled = compile_filename(template, context)
        self.filename_preview_label.setText(compiled.filename)

    def _update_session_labels(self) -> None:
        count = len(self.session_library.records)
        self.session_stats_label.setText(
            f"{count} photo{'s' if count != 1 else ''}\n"
            f"Series: {self.session_input.text().strip() or 'Untitled'}\n"
            f"Auto reconnect: {'On' if self.auto_reconnect_check.isChecked() else 'Off'}"
        )
        self.session_path_label.setText(f"Session folder: {self.session_library.session_root}")

    def _start_new_session(self) -> None:
        self.session_library = self._create_session_library(self.session_input.text().strip() or "Session")
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

    def _browse_hot_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose hot folder", self.hot_folder_input.text() or str(Path.home()))
        if not folder:
            return
        self.hot_folder_input.setText(folder)
        self.hot_folder_check.setChecked(True)
        self._on_hot_folder_toggled(True)

    def _browse_sdk_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose Canon SDK folder", self.sdk_path_input.text() or str(Path.home()))
        if folder:
            self.sdk_path_input.setText(folder)

    def _on_hot_folder_toggled(self, enabled: bool) -> None:
        self.hot_folder.set_folder(self.hot_folder_input.text().strip() if enabled else None)
        self._persist_config()
        self._update_session_labels()

    def _on_hot_folder_path_changed(self) -> None:
        if self.hot_folder_check.isChecked():
            self.hot_folder.set_folder(self.hot_folder_input.text().strip())
        self._persist_config()

    def _push_runtime_options(self) -> None:
        self.camera_manager.update_runtime_options(
            auto_reconnect=self.auto_reconnect_check.isChecked(),
            simulator_auto_capture_seconds=self.sim_capture_spin.value(),
            edsdk_path=self.sdk_path_input.text().strip(),
        )
        self._persist_config()
        self._update_session_labels()

    def _scan_hot_folder(self) -> None:
        if not self.hot_folder_check.isChecked():
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
        self.config.backend = str(self.backend_combo.currentData() or "simulator")
        self.config.event_name = self.event_input.text().strip() or "Event"
        self.config.booth_name = self.booth_input.text().strip() or self.config.booth_name
        self.config.session_name = self.session_input.text().strip() or "Session"
        self.config.naming_template = self.template_input.text().strip() or self.config.naming_template
        self.config.hot_folder_enabled = self.hot_folder_check.isChecked()
        self.config.hot_folder_path = self.hot_folder_input.text().strip()
        self.config.auto_reconnect = self.auto_reconnect_check.isChecked()
        self.config.simulator_auto_capture_seconds = self.sim_capture_spin.value()
        self.config.edsdk_path = self.sdk_path_input.text().strip()
        self.config.selected_photo_id = self.selected_photo_id
        self.config.zoom_enabled = self.zoom_toggle.isChecked()
        self.config_store.save(self.config)

    def status_message(self, message: str) -> None:
        if self.statusBar():
            self.statusBar().showMessage(message, 5000)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

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
