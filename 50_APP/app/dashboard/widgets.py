"""Reusable display widgets for the dashboard."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Property, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

CURRENCY_ICON_DIR = Path(__file__).parent / "assets" / "currency_icons"


def classify_cli_result(data) -> tuple[bool, str]:
    """(성공 여부, 실패 사유) - success unless the CLI response carries an error/rejection."""
    if isinstance(data, dict):
        if "error" in data:
            return False, str(data.get("message", data["error"]))
        status = data.get("status")
        if status and status != "accepted":
            return False, str(data.get("message", status))
    return True, ""


class ToggleSwitch(QAbstractButton):
    """A small iOS-style slide switch. Checked state doesn't persist anything by itself -
    the dashboard uses it as a retry action ("slide on to try connecting again")."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 24)
        self._offset = 3
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(150)
        self.toggled.connect(self._animate_to)

    def _animate_to(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(25 if checked else 3)
        self._anim.start()

    def get_offset(self) -> int:
        return self._offset

    def set_offset(self, value: int) -> None:
        self._offset = value
        self.update()

    offset = Property(int, get_offset, set_offset)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt override, keep knob in sync
        super().setChecked(checked)
        self._offset = 25 if checked else 3
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2ecc71") if self.isChecked() else QColor("#5a5a60"))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(self._offset, 3, 18, 18)


class FlowLayout(QLayout):
    """Qt's standard "Flow Layout" recipe: lays child widgets left-to-right, wrapping to a new
    row whenever the next one wouldn't fit the available width, and reports heightForWidth so
    the container grows to fit however many rows that takes - used by InstrumentBar
    (music_panel.py) so the owned-instrument button row becomes N rows instead of one
    horizontally-scrolling row as the window width changes or the instrument count grows."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 6):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items: list = []

    def addItem(self, item) -> None:  # noqa: N802 - Qt override
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - Qt override
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802 - Qt override
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802 - Qt override
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt override
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt override
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt override
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            next_x = x + item.sizeHint().width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + spacing
                next_x = x + item.sizeHint().width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom


class Toast(QLabel):
    """Small floating notification anchored to the bottom-right of its parent."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setStyleSheet(
            "background-color: rgba(40, 40, 45, 235); color: white; padding: 10px 16px;"
            "border-radius: 8px; font-size: 13px;"
        )
        self.hide()

    def show_message(self, text: str, msec: int = 2000) -> None:
        self.setText(text)
        self.adjustSize()
        parent_rect = self.parentWidget().rect()
        self.move(parent_rect.width() - self.width() - 24, parent_rect.height() - self.height() - 24)
        self.show()
        self.raise_()
        QTimer.singleShot(msec, self.hide)


def _load_currency_manifest() -> dict:
    manifest_path = CURRENCY_ICON_DIR / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


# Currency display rules (user call, 2026-09-18): these entries are either seasonal/event
# stuff that isn't worth a permanent row, or the suffix after the prefix rotates too often
# to hardcode - see 10_RESEARCH/03_cli_command_reference_2026-09-17.md for the full list.
HIDDEN_CURRENCY_NAMES = frozenset(
    {
        "원정의 증거: 글라스기브넨 레이드",
        "원정의 증거: 타바르타스 레이드",
        "심연의 화석",
        "붉은 심연의 화석",
        "심연의 마석",
        "변이된 심연의 화석",
        "웨카",
    }
)
TRUNCATED_PREFIXES = ("패키지 포인트",)


def _display_name_for(name: str) -> str:
    for prefix in TRUNCATED_PREFIXES:
        if name.startswith(prefix):
            return prefix
    return name


class CurrencyColumn(QScrollArea):
    """Single-column, vertically scrolling list of currency icon + name + amount rows,
    meant to sit along the left edge of the window."""

    WIDTH = 260

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFixedWidth(self.WIDTH)
        self.setFrameShape(QFrame.NoFrame)
        self._manifest = _load_currency_manifest()

        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(3)
        self.setWidget(inner)

    def set_data(self, rows) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not isinstance(rows, list):
            message = rows.get("message", rows) if isinstance(rows, dict) else str(rows)
            self._layout.addWidget(QLabel(f"⚠️ 재화 조회 실패: {message}"))
            self._layout.addStretch(1)
            return

        for row in rows:
            name = str(row.get("DisplayName", ""))
            if name in HIDDEN_CURRENCY_NAMES:
                continue
            amount = row.get("Amount", 0)
            self._layout.addWidget(self._make_row(name, amount))
        self._layout.addStretch(1)

    # 80% of the original 26px icon (user call, 2026-09-18 - rows were too tall / too much
    # scrolling), with tighter chip padding/spacing to match.
    ICON_SIZE = 21

    def _make_row(self, name: str, amount) -> QWidget:
        chip = QFrame()
        chip.setStyleSheet("QFrame { background-color: #2b2b30; border-radius: 8px; }")
        chip.setToolTip(name)
        layout = QHBoxLayout(chip)
        layout.setContentsMargins(6, 3, 8, 3)
        layout.setSpacing(6)

        icon_label = QLabel()
        icon_label.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        fname = self._manifest.get(name)  # icon lookup always uses the full, untruncated name
        if fname:
            pixmap = QPixmap(str(CURRENCY_ICON_DIR / fname))
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(self.ICON_SIZE, self.ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        layout.addWidget(icon_label)

        name_label = QLabel(_display_name_for(name))
        name_label.setStyleSheet("color: #ccc; font-size: 11px;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label, 1)

        amount_text = f"{amount:,}" if isinstance(amount, int) else str(amount)
        amount_label = QLabel(amount_text)
        amount_label.setStyleSheet("color: #eee; font-weight: 600; font-size: 12px;")
        amount_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(amount_label)

        return chip
