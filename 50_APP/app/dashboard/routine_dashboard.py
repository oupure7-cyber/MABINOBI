"""Standalone floating window that mirrors AlteringRoutineWorker's state while it runs - a
materials table (전체 자원 리스트, inventory+account+character storage summed - same numbers
the worker itself decides on) and a per-facility queue fill bar (n/7), both driven purely by
the worker's `snapshot` signal (see altering_routine.py's module docstring: this window never
calls the CLI itself, to avoid two callers hitting MabinogiMobile_CLI.exe at once).

Lifecycle (user-specified, 2026-09-18):
- Opens automatically alongside the routine (gather_panel.py creates+shows it when the
  routine starts) as a separate top-level window from the main 마비노비 window, so it can be
  dragged to wherever's convenient while watching the game.
- If the routine auto-stops itself (`blocked` - e.g. an unexpected popup), the window stays
  open but swaps its content for a red "루틴이 중단되었습니다" alert - the per-item counts
  disappear, since they're no longer being updated and would just be stale.
- If the user manually stops the routine (the button in the main window), this window closes
  itself entirely instead.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .altering_routine import CHAINS, QUEUE_CAPACITY, AlteringRoutineWorker
from .item_icons import item_icon


def _ordered_material_names() -> list[str]:
    """Display order grouped by chain (완제품, 중간재, 직접재료, 원자재), de-duplicated - not
    alphabetical, so related rows sit together (e.g. 옷감/옷감+/양털 stay adjacent even though
    양털 also feeds the 옷감 intermediate)."""
    names: list[str] = []
    seen: set[str] = set()
    for chain in CHAINS:
        for name in (chain.end_product, chain.intermediate, chain.end_direct_material, *[p.raw_material for p in chain.paths]):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


class RoutineDashboard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("가공 무한 대시보드")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(320, 480)

        self._blocked = False
        self._material_names = _ordered_material_names()
        self._material_row: dict[str, int] = {}
        self._queue_bar: dict[str, QProgressBar] = {}
        self._queue_label: dict[str, QLabel] = {}

        outer = QVBoxLayout(self)

        self._alert = QLabel("")
        self._alert.setWordWrap(True)
        self._alert.setStyleSheet("color: #ff5555; font-weight: 700; font-size: 13px; padding: 8px;")
        self._alert.hide()
        outer.addWidget(self._alert)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        materials_box = QGroupBox("재료/생산물 현황 (인벤토리+캐릭터창고+계정창고 합계)")
        materials_layout = QVBoxLayout(materials_box)
        table = QTableWidget(len(self._material_names), 2)
        table.setHorizontalHeaderLabels(["이름", "수량"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.horizontalHeader().setStretchLastSection(True)
        for row, name in enumerate(self._material_names):
            table.setItem(row, 0, QTableWidgetItem(item_icon(name), name))
            count_item = QTableWidgetItem("-")
            table.setItem(row, 1, count_item)
            self._material_row[name] = row
        self._table = table
        materials_layout.addWidget(table)
        content_layout.addWidget(materials_box, 1)

        queue_box = QGroupBox("가공 시설 대기열")
        queue_layout = QVBoxLayout(queue_box)
        for chain in CHAINS:
            label = QLabel(f"{chain.label} ({chain.facility}): -/{QUEUE_CAPACITY}")
            bar = QProgressBar()
            bar.setRange(0, QUEUE_CAPACITY)
            bar.setTextVisible(False)
            queue_layout.addWidget(label)
            queue_layout.addWidget(bar)
            self._queue_label[chain.key] = label
            self._queue_bar[chain.key] = bar
        content_layout.addWidget(queue_box)

        outer.addWidget(self._content, 1)

    def attach(self, worker: AlteringRoutineWorker) -> None:
        worker.snapshot.connect(self._on_snapshot)
        worker.blocked.connect(self._on_blocked)
        worker.stopped.connect(self._on_stopped)

    def _on_snapshot(self, snap: dict) -> None:
        if self._blocked:
            return
        materials = snap.get("materials", {})
        for name, row in self._material_row.items():
            if name in materials:
                self._table.item(row, 1).setText(str(materials[name]))
        queue = snap.get("queue", {})
        queue_completed = snap.get("queue_completed", {})
        for key, n in queue.items():
            bar = self._queue_bar.get(key)
            label = self._queue_label.get(key)
            if bar is None or label is None:
                continue
            bar.setValue(n)
            done = queue_completed.get(key, 0)
            chain = next(c for c in CHAINS if c.key == key)
            text = f"{chain.label} ({chain.facility}): {n}/{QUEUE_CAPACITY}"
            if done:
                text += f" · 완료 {done}개 회수 대기"
                label.setStyleSheet("color: #f0c060; font-weight: 600;")
            else:
                label.setStyleSheet("")
            label.setText(text)

    def _on_blocked(self, kind: str) -> None:
        self._blocked = True
        self._content.hide()
        self._alert.setText(f"⚠️ 가공 무한 루틴이 자동으로 중단되었습니다\n\n사유: {kind}\n\n게임 화면을 확인해주세요.")
        self._alert.show()

    def _on_stopped(self) -> None:
        if not self._blocked:
            self.close()
