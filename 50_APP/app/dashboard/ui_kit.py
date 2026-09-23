"""Shared style/widget-builder helpers for the modern UI (modern_window.py and any dialog
that must visually match it, e.g. character_manager.py). Kept separate from
modern_window.py so those dialogs can import this without a circular import."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel, QPushButton, QTableWidget, QHeaderView, QStyledItemDelegate

OWNED_COUNT_ROLE = Qt.UserRole + 11
OWNED_COUNT_COLOR = '#ffdf70'


class OwnedCountDelegate(QStyledItemDelegate):
    """Keep quantities yellow even when their entire row is selected."""
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(OWNED_COUNT_ROLE):
            color = QColor(OWNED_COUNT_COLOR)
            option.palette.setColor(QPalette.Text, color)
            option.palette.setColor(QPalette.HighlightedText, color)


STYLE = """
QWidget { background: #121e23; color: #e4e9eb; font-family: 'Malgun Gothic'; font-size: 14px; }
QMainWindow { background: #121e23; }
QLabel { background: transparent; }
QLabel[heading="true"] { font-size: 19px; font-weight: 700; padding: 6px 0; }
QPushButton { background: #19292f; border: 1px solid #3a5059; border-radius: 4px; padding: 6px 12px; }
QPushButton:hover { background: #253b42; border-color: #6a9186; }
QPushButton:checked { color: #90dcb5; background: #1c3a32; border-color: #69b18c; }
QPushButton:disabled { color: #6b7a80; border-color: #293a41; }
QTableWidget QPushButton { padding: 3px; }
QTableWidget::item { border-bottom: 1px solid #293b43; padding: 4px; }
QLineEdit, QComboBox { background: #101b20; border: 1px solid #3a5059; border-radius: 4px; padding: 7px; }
QTableWidget, QListWidget, QPlainTextEdit, QTreeWidget { background: #121e23; border: 1px solid #293b43; gridline-color: #293b43; selection-background-color: #24483c; }
QListWidget::item { padding: 8px; border-bottom: 1px solid #293b43; }
QTreeWidget::item { padding: 4px; border-bottom: 1px solid #293b43; }
QHeaderView::section { background: #20313a; color: #bdcbd0; border: none; padding: 7px; }
QTabWidget::pane { border: none; border-top: 1px solid #33484e; }
QTabBar::tab { padding: 12px 27px; color: #bbc6cb; border-bottom: 3px solid transparent; }
QTabBar::tab:selected { color: #8bd8ae; border-bottom: 3px solid #8bd8ae; }
QScrollBar:vertical { background: #132027; width: 9px; }
QScrollBar::handle:vertical { background: #39515a; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QFrame#infoPanel { border: 1px solid #54706f; background: #17272d; }
QSplitter::handle { background: #30454c; width: 1px; }
"""

def heading(text):
    label = QLabel(text)
    label.setProperty('heading', True)
    return label

def button(text, callback):
    b = QPushButton(text)
    b.clicked.connect(callback)
    return b

def table(headers, widget_class=QTableWidget):
    t = widget_class(0, len(headers))
    t.setIconSize(QSize(26, 26))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().hide()
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setShowGrid(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    return t
