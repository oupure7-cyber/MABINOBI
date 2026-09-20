"""One family's target-tier slider - "<-----●----->" per 금속/목재/가죽/옷감 (user sketch,
2026-09-20), replacing the old fixed 강철괴/목재+/옷감+/가죽+ ceiling with a runtime-adjustable
one. Dragging the handle to a node sets how far up that family's chain
(`altering_routine.FAMILIES`) the "가공 무한" routine should keep synthesizing - see that
module's docstring for the promotion rule this drives.

Plain QSlider (this is the first use of one in the app - confirmed no existing QSS collision)
with a row of tier-name labels underneath instead of a fully custom-painted widget: much less
code, native drag/keyboard support for free, and the labels solve the actual readability need
(a bare slider wouldn't tell the user what a given notch even means) without hand-rolled hit
testing.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from .altering_routine import Family

ACTIVE_STYLE = "color: #8bd8ae; font-weight: 700;"
INACTIVE_STYLE = "color: #6b7a80; font-weight: 400;"

SLIDER_STYLE = """
QSlider::groove:horizontal { height: 4px; background: #3a5059; border-radius: 2px; }
QSlider::sub-page:horizontal { height: 4px; background: #8bd8ae; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    background: #8bd8ae; border: 2px solid #121e23;
}
QSlider::handle:horizontal:hover { background: #a6e6c4; }
"""


class TierTargetControl(QWidget):
    target_changed = Signal(int)  # tier index within family.tiers

    def __init__(self, family: Family, parent=None):
        super().__init__(parent)
        self.family = family

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(2)

        self._heading = QLabel()
        self._heading.setStyleSheet("font-weight: 700; padding-bottom: 2px;")
        outer.addWidget(self._heading)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(len(family.tiers) - 1)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(1)
        self._slider.setTickInterval(1)
        self._slider.setTickPosition(QSlider.TicksBelow)
        self._slider.setStyleSheet(SLIDER_STYLE)
        self._slider.setValue(family.default_target_idx)
        self._slider.valueChanged.connect(self._on_value_changed)
        outer.addWidget(self._slider)

        labels_row = QHBoxLayout()
        labels_row.setSpacing(0)
        self._labels: list[QLabel] = []
        for tier in family.tiers:
            label = QLabel(tier.name)
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            labels_row.addWidget(label, 1)
            self._labels.append(label)
        outer.addLayout(labels_row)

        self._refresh_labels(family.default_target_idx)

    def value(self) -> int:
        return self._slider.value()

    def _on_value_changed(self, idx: int) -> None:
        self._refresh_labels(idx)
        self.target_changed.emit(idx)

    def _refresh_labels(self, idx: int) -> None:
        self._heading.setText(f"{self.family.label} 목표: {self.family.tiers[idx].name}")
        for i, label in enumerate(self._labels):
            label.setStyleSheet(ACTIVE_STYLE if i == idx else INACTIVE_STYLE)
