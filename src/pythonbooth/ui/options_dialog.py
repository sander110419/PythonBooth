from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import AppConfig


class OptionsDialog(QDialog):
    """Compact setup dialog for one-time and semi-constant booth options."""

    def __init__(self, parent: QWidget | None = None, *, config: AppConfig | None = None):
        super().__init__(parent)
        self.setWindowTitle("PythonBooth Options")
        self.setModal(True)
        self.setMinimumWidth(760)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._build_ui()
        if config is not None:
            self.set_from_config(config)
        self._update_hot_folder_enabled_state(self.hot_folder_check.isChecked())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        heading = QVBoxLayout()
        title = QLabel("Options")
        title.setObjectName("TitleLabel")
        subtitle = QLabel("Session setup, capture behavior, and external paths.")
        subtitle.setObjectName("MutedText")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        root.addLayout(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        content_layout.addWidget(self._build_session_group())
        content_layout.addWidget(self._build_capture_group())
        content_layout.addWidget(self._build_paths_group())
        content_layout.addStretch(1)

        root.addWidget(scroll, 1)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        root.addWidget(self.button_box)

        self.setStyleSheet(
            """
            QDialog {
                background: #0b1017;
                color: #edf2ff;
            }
            QGroupBox {
                background: rgba(17, 26, 39, 210);
                border: 1px solid rgba(127, 214, 194, 42);
                border-radius: 18px;
                margin-top: 14px;
                padding: 14px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #dce7ff;
            }
            QLabel#MutedText {
                color: #90a0b9;
                font-weight: 400;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(175, 190, 216, 0.18);
                border-radius: 12px;
                padding: 9px 10px;
                min-height: 18px;
            }
            QCheckBox {
                spacing: 10px;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(210, 220, 245, 0.14);
                border-radius: 12px;
                padding: 9px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.11);
            }
            """
        )

    def _build_session_group(self) -> QGroupBox:
        group = QGroupBox("Booth Setup")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(12)

        self.backend_combo = QComboBox()
        self.backend_combo.addItem("Canon EDSDK", "canon")
        self.backend_combo.addItem("Simulator", "simulator")

        self.event_edit = QLineEdit()
        self.booth_edit = QLineEdit()
        self.session_edit = QLineEdit()
        self.naming_template_edit = QLineEdit()

        layout.addRow("Backend", self.backend_combo)
        layout.addRow("Event name", self.event_edit)
        layout.addRow("Booth / machine", self.booth_edit)
        layout.addRow("Session name", self.session_edit)
        layout.addRow("Filename template", self.naming_template_edit)
        return group

    def _build_capture_group(self) -> QGroupBox:
        group = QGroupBox("Capture Behavior")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        self.auto_reconnect_check = QCheckBox("Auto reconnect to camera")
        self.auto_reconnect_check.setChecked(True)
        layout.addWidget(self.auto_reconnect_check)

        self.sim_capture_spin = QSpinBox()
        self.sim_capture_spin.setRange(0, 60)
        self.sim_capture_spin.setSuffix(" s")

        sim_row = QHBoxLayout()
        sim_row.addWidget(QLabel("Simulator auto-capture interval"))
        sim_row.addStretch(1)
        sim_row.addWidget(self.sim_capture_spin)
        layout.addLayout(sim_row)

        return group

    def _build_paths_group(self) -> QGroupBox:
        group = QGroupBox("Storage & Paths")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(12)

        self.hot_folder_check = QCheckBox("Enable hot-folder import")
        self.hot_folder_check.toggled.connect(self._update_hot_folder_enabled_state)

        self.hot_folder_edit = QLineEdit()
        self.hot_folder_browse_button = QPushButton("Browse")
        self.hot_folder_browse_button.clicked.connect(self._browse_hot_folder)
        self.hot_folder_row = self._path_row(self.hot_folder_edit, self.hot_folder_browse_button)

        self.sdk_path_edit = QLineEdit()
        self.sdk_browse_button = QPushButton("Browse")
        self.sdk_browse_button.clicked.connect(self._browse_sdk_path)
        self.sdk_row = self._path_row(self.sdk_path_edit, self.sdk_browse_button)

        layout.addRow(self.hot_folder_check)
        layout.addRow("Hot folder", self.hot_folder_row)
        layout.addRow("Canon SDK path", self.sdk_row)
        return group

    def _path_row(self, edit: QLineEdit, button: QPushButton) -> QWidget:
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(edit, 1)
        row.addWidget(button)
        return widget

    def _browse_hot_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select hot folder", self.hot_folder_edit.text() or str(Path.home()))
        if folder:
            self.hot_folder_edit.setText(folder)
            self.hot_folder_check.setChecked(True)

    def _browse_sdk_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Canon SDK folder", self.sdk_path_edit.text() or str(Path.home()))
        if folder:
            self.sdk_path_edit.setText(folder)

    def _update_hot_folder_enabled_state(self, enabled: bool) -> None:
        self.hot_folder_edit.setEnabled(enabled)
        self.hot_folder_browse_button.setEnabled(enabled)

    def set_options(self, options: Mapping[str, Any]) -> None:
        backend = str(options.get("backend", "simulator"))
        backend_index = self.backend_combo.findData(backend)
        if backend_index >= 0:
            self.backend_combo.setCurrentIndex(backend_index)

        self.event_edit.setText(str(options.get("event_name", "")))
        self.booth_edit.setText(str(options.get("booth_name", "")))
        self.session_edit.setText(str(options.get("session_name", "")))
        self.naming_template_edit.setText(str(options.get("naming_template", "")))
        self.auto_reconnect_check.setChecked(bool(options.get("auto_reconnect", True)))
        self.hot_folder_check.setChecked(bool(options.get("hot_folder_enabled", False)))
        self.hot_folder_edit.setText(str(options.get("hot_folder_path", "")))
        self.sim_capture_spin.setValue(int(float(options.get("simulator_auto_capture_seconds", 0) or 0)))
        self.sdk_path_edit.setText(str(options.get("edsdk_path", "")))
        self._update_hot_folder_enabled_state(self.hot_folder_check.isChecked())

    def set_from_config(self, config: AppConfig) -> None:
        self.set_options(
            {
                "backend": config.backend,
                "event_name": config.event_name,
                "booth_name": config.booth_name,
                "session_name": config.session_name,
                "naming_template": config.naming_template,
                "auto_reconnect": config.auto_reconnect,
                "hot_folder_enabled": config.hot_folder_enabled,
                "hot_folder_path": config.hot_folder_path,
                "simulator_auto_capture_seconds": config.simulator_auto_capture_seconds,
                "edsdk_path": config.edsdk_path,
            }
        )

    def options_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend_combo.currentData(),
            "event_name": self.event_edit.text().strip(),
            "booth_name": self.booth_edit.text().strip(),
            "session_name": self.session_edit.text().strip(),
            "naming_template": self.naming_template_edit.text().strip(),
            "auto_reconnect": self.auto_reconnect_check.isChecked(),
            "hot_folder_enabled": self.hot_folder_check.isChecked(),
            "hot_folder_path": self.hot_folder_edit.text().strip(),
            "simulator_auto_capture_seconds": float(self.sim_capture_spin.value()),
            "edsdk_path": self.sdk_path_edit.text().strip(),
        }

