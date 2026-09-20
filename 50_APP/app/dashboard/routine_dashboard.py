"""Compact N-tier workshop controls and a read-only view of worker snapshots.

Inventory includes both storage locations. This view never calls the game CLI.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QGroupBox, QHeaderView, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .altering_routine import FAMILIES, QUEUE_CAPACITY, AlteringRoutineWorker
from .tier_target_control import TierTargetControl
from .item_icons import item_icon


def _ordered_material_names() -> list[str]:
    """Keep a product next to its intermediate and raw materials."""
    names: list[str] = []
    for family in FAMILIES:
        # All seven tiers remain inspectable without inflating the panel: the
        # bounded table scrolls, with each family in production order.
        for tier in family.tiers:
            for name in (tier.name, *(ingredient.material for option in tier.recipes
                                      for ingredient in option.inputs)):
                if name not in names:
                    names.append(name)
    return names


class FacilitySlots(QWidget):
    """Seven small slots; unfinished occupancy is not a completion percentage."""
    COLORS = {
        'empty': '#263a41', 'occupied': '#66ae92',
        'completed': '#d6b56d', 'unknown': '#3a4a50',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.states = ['unknown'] * QUEUE_CAPACITY
        self.setFixedSize(112, 20)
        self.setAccessibleName('생산 시설 슬롯')

    def update_counts(self, occupied: int, completed: int) -> None:
        occupied = max(0, min(QUEUE_CAPACITY, occupied))
        completed = max(0, min(occupied, completed))
        self.states = (['completed'] * completed
                       + ['occupied'] * (occupied - completed)
                       + ['empty'] * (QUEUE_CAPACITY - occupied))
        self.setToolTip(f'회수 가능 {completed} · 가공/대기 {occupied - completed} · 빈 슬롯 {QUEUE_CAPACITY - occupied}')
        self.setAccessibleDescription(self.toolTip())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for index, state in enumerate(self.states):
            painter.setBrush(QColor(self.COLORS[state]))
            painter.drawRoundedRect(index * 16, 4, 12, 12, 2, 2)


class RoutineDashboard(QWidget):
    snapshot_received = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle('무한가공소 현황')
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(680, 720)
        self._blocked = False
        self._material_names = _ordered_material_names()
        self._material_row: dict[str, int] = {}
        self._material_column: dict[str, int] = {}
        self._queue_slots: dict[str, FacilitySlots] = {}
        self._queue_label: dict[str, QLabel] = {}
        self._queue_count: dict[str, QLabel] = {}
        self._queue_icons: dict[str, QLabel] = {}
        self._controls: dict[str, TierTargetControl] = {}
        self._target_worker: AlteringRoutineWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(8)
        self._alert = QLabel('')
        self._alert.setWordWrap(True)
        self._alert.setStyleSheet('color: #eeb38e; padding: 8px;')
        self._alert.hide()
        outer.addWidget(self._alert)

        self._content = QWidget()
        content = QVBoxLayout(self._content)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(7)
        targets_box = QGroupBox('목표 등급 설정')
        targets_box.setStyleSheet('QGroupBox { font-size: 12px; } QLabel { font-size: 12px; }')
        targets_layout = QVBoxLayout(targets_box)
        targets_layout.setContentsMargins(8, 12, 8, 6)
        targets_layout.setSpacing(3)
        for family in FAMILIES:
            control = TierTargetControl(family)
            control.target_changed.connect(self._on_target_changed(family.key))
            targets_layout.addWidget(control)
            self._controls[family.key] = control
        content.addWidget(targets_box)

        heading = QHBoxLayout()
        heading.addWidget(QLabel('재료 · 생산물'))
        caption = QLabel('가방 + 캐릭터 · 계정 창고 합계')
        caption.setStyleSheet('color: #8ea6ad; font-size: 11px;')
        heading.addStretch()
        heading.addWidget(caption)
        content.addLayout(heading)

        rows = (len(self._material_names) + 1) // 2
        table = QTableWidget(rows, 4)
        table.setHorizontalHeaderLabels(['아이템', '보유', '아이템', '보유'])
        table.setIconSize(QSize(20, 20))
        table.setShowGrid(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.verticalHeader().hide()
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.verticalHeader().setDefaultSectionSize(27)
        table.verticalHeader().setMinimumSectionSize(27)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.horizontalHeader().setFixedHeight(27)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for column in (1, 3):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Fixed)
            table.setColumnWidth(column, 70)
        table.setStyleSheet('QTableWidget::item { padding: 2px 5px; font-size: 12px; } QHeaderView::section { padding: 4px 5px; font-size: 11px; }')
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        table.setMinimumHeight(135)
        table.setMaximumHeight(min(27 * (rows + 1) + 3, 192))
        for index, name in enumerate(self._material_names):
            row, column = index % rows, (index // rows) * 2
            title = QTableWidgetItem(item_icon(name), name)
            title.setToolTip(name)
            table.setItem(row, column, title)
            value = QTableWidgetItem('—')
            value.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, column + 1, value)
            self._material_row[name] = row
            self._material_column[name] = column + 1
        self._table = table
        content.addWidget(table, 1)

        facilities_header = QHBoxLayout()
        facilities_header.setContentsMargins(0, 5, 0, 0)
        facilities_header.addWidget(QLabel('생산 시설'))
        facilities_header.addStretch()
        legend = QLabel('<span style="color:#66ae92">■ 가공/대기</span>　<span style="color:#d6b56d">■ 회수 가능</span>　<span style="color:#7d9199">□ 빈 슬롯</span>')
        legend.setStyleSheet('font-size: 10px;')
        facilities_header.addWidget(legend)
        content.addLayout(facilities_header)

        for family in FAMILIES:
            row_widget = QWidget()
            row_widget.setFixedHeight(31)
            row_widget.setStyleSheet('QWidget { background: #17272d; border-radius: 3px; } QLabel { background: transparent; font-size: 12px; }')
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(7, 1, 7, 1)
            row.setSpacing(7)
            icon = QLabel()
            icon.setFixedSize(20, 20)
            icon.setPixmap(item_icon(family.tiers[family.default_target_idx].name).pixmap(20, 20))
            name = QLabel(family.label)
            name.setMinimumWidth(48)
            name.setToolTip(family.facility)
            slots = FacilitySlots()
            count = QLabel('— / 7')
            count.setMinimumWidth(37)
            count.setStyleSheet('color: #9aadb4; font-size: 11px;')
            status = QLabel('작업 시작 후 표시')
            status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            status.setStyleSheet('color: #8ea6ad; font-size: 11px;')
            status.setMinimumWidth(0)
            row.addWidget(icon)
            row.addWidget(name)
            row.addWidget(slots)
            row.addWidget(count)
            row.addWidget(status, 1)
            self._queue_icons[family.key] = icon
            self._queue_slots[family.key] = slots
            self._queue_label[family.key] = status
            self._queue_count[family.key] = count
            content.addWidget(row_widget)

        content.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setMinimumHeight(160)
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, 1)

    def attach(self, worker: AlteringRoutineWorker) -> None:
        worker.snapshot.connect(self._on_snapshot)
        worker.blocked.connect(self._on_blocked)
        worker.stopped.connect(self._on_stopped)
        self.wire_targets(worker)

    def wire_targets(self, worker: AlteringRoutineWorker) -> None:
        """Use current targets for this worker; future drags reach only this one."""
        self._target_worker = worker
        for family_key, control in self._controls.items():
            worker.set_target(family_key, control.value())

    def _on_target_changed(self, family_key: str):
        def handler(idx: int) -> None:
            family = next(family for family in FAMILIES if family.key == family_key)
            icon = self._queue_icons.get(family_key)
            if icon is not None:
                icon.setPixmap(item_icon(family.tiers[idx].name).pixmap(20, 20))
            if self._target_worker is not None:
                self._target_worker.set_target(family_key, idx)
        return handler

    def _on_snapshot(self, snap: dict) -> None:
        if self._blocked:
            return
        materials = snap.get('materials', {})
        for name, row in self._material_row.items():
            if name in materials:
                value = materials[name]
                self._table.item(row, self._material_column[name]).setText(f'{value:,}' if isinstance(value, int) else str(value))
        queue = snap.get('queue', {})
        completed = snap.get('queue_completed', {})
        for key, occupied in queue.items():
            if key not in self._queue_slots:
                continue
            occupied = max(0, min(QUEUE_CAPACITY, int(occupied)))
            done = max(0, min(occupied, int(completed.get(key, 0))))
            self._queue_slots[key].update_counts(occupied, done)
            self._queue_count[key].setText(f'{occupied} / {QUEUE_CAPACITY}')
            label = self._queue_label[key]
            if done:
                text = f'회수 {done} · 가공/대기 {occupied - done}'
                color = '#d6b56d'
            elif occupied:
                text = f'가공/대기 {occupied} · 빈 슬롯 {QUEUE_CAPACITY - occupied}'
                color = '#9abbb0'
            else:
                text, color = '등록된 작업 없음', '#8ea6ad'
            label.setText(text)
            label.setToolTip(text)
            label.setStyleSheet(f'color: {color}; font-size: 11px;')
        self.snapshot_received.emit(snap)

    def _on_blocked(self, kind: str) -> None:
        self._blocked = True
        self._content.hide()
        self._alert.setText(f'무한가공소가 중단되었습니다\n사유: {kind}\n게임 화면을 확인해주세요.')
        self._alert.show()

    def _on_stopped(self) -> None:
        if not self._blocked:
            self.close()
