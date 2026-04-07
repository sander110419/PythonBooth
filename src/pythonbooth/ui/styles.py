from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


APP_STYLESHEET = """
QWidget {
    background: #0b1017;
    color: #edf2ff;
    font-family: "Aptos", "Segoe UI", "Noto Sans", sans-serif;
    font-size: 14px;
}
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0b1017, stop:0.4 #101927, stop:1 #152434);
}
QFrame#Card {
    background: rgba(17, 26, 39, 210);
    border: 1px solid rgba(127, 214, 194, 48);
    border-radius: 22px;
}
QFrame#TimelineCard {
    background: rgba(10, 14, 20, 235);
    border: 1px solid rgba(127, 214, 194, 38);
    border-radius: 22px;
}
QLabel#TitleLabel {
    font-size: 32px;
    font-weight: 700;
}
QLabel#SectionTitle {
    font-size: 16px;
    font-weight: 600;
    color: #dce7ff;
}
QLabel#MutedText {
    color: #90a0b9;
}
QLabel#StatusPill[statusState="connected"] {
    background: rgba(85, 197, 126, 38);
    color: #96efb7;
    border: 1px solid rgba(150, 239, 183, 60);
    border-radius: 16px;
    padding: 8px 14px;
    font-weight: 600;
}
QLabel#StatusPill[statusState="error"] {
    background: rgba(242, 112, 107, 28);
    color: #ffb1aa;
    border: 1px solid rgba(255, 177, 170, 60);
    border-radius: 16px;
    padding: 8px 14px;
    font-weight: 600;
}
QLabel#StatusPill[statusState="idle"],
QLabel#StatusPill[statusState="disconnected"] {
    background: rgba(143, 156, 181, 28);
    color: #d9e1f3;
    border: 1px solid rgba(180, 193, 215, 44);
    border-radius: 16px;
    padding: 8px 14px;
    font-weight: 600;
}
QLineEdit, QComboBox, QDoubleSpinBox {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(175, 190, 216, 0.18);
    border-radius: 14px;
    padding: 10px 12px;
    selection-background-color: #45c3ac;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus {
    border: 1px solid rgba(127, 214, 194, 0.85);
}
QPushButton, QToolButton {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(210, 220, 245, 0.14);
    border-radius: 14px;
    padding: 10px 14px;
    font-weight: 600;
}
QToolButton::menu-indicator {
    image: none;
    width: 0;
}
QPushButton:hover, QToolButton:hover {
    background: rgba(255, 255, 255, 0.11);
}
QPushButton[accent="true"] {
    background: #45c3ac;
    color: #081018;
    border: none;
}
QPushButton[accent="true"]:hover {
    background: #64d7c1;
}
QCheckBox {
    spacing: 10px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 1px solid rgba(200, 210, 230, 0.28);
    background: rgba(255, 255, 255, 0.06);
}
QCheckBox::indicator:checked {
    background: #45c3ac;
    border: 1px solid #45c3ac;
}
QListWidget {
    background: transparent;
    border: none;
}
QMenu {
    background: rgba(11, 16, 23, 240);
    border: 1px solid rgba(127, 214, 194, 42);
    border-radius: 14px;
    padding: 8px;
}
QMenu::item {
    padding: 10px 14px;
    border-radius: 10px;
}
QMenu::item:selected {
    background: rgba(69, 195, 172, 0.2);
}
QScrollBar:horizontal, QScrollBar:vertical {
    background: transparent;
    width: 14px;
    height: 14px;
    margin: 0;
}
QScrollBar::handle:horizontal, QScrollBar::handle:vertical {
    background: rgba(140, 154, 178, 0.35);
    border-radius: 7px;
    min-width: 30px;
    min-height: 30px;
}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    border: none;
}
QStatusBar {
    background: rgba(8, 12, 18, 210);
    color: #dce7ff;
}
"""


def apply_theme(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#0b1017"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#101927"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#152434"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#edf2ff"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#101927"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#edf2ff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#45c3ac"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#081018"))
    app.setPalette(palette)
    app.setStyleSheet(APP_STYLESHEET)
