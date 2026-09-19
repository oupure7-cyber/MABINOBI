"""Standalone floating window that mirrors AlteringRoutineWorker's state while it runs - the
per-family target-tier sliders (`TierTargetControl`, what actually drives the routine's runtime
behavior - see altering_routine.py's module docstring for the promotion rule) and a
per-facility queue fill bar (n/7), the latter driven purely by the worker's `snapshot` signal
(this window never calls the CLI itself, to avoid two callers hitting MabinogiMobile_CLI.exe at
once).

The old "재료/생산물 현황" materials table that used to live here was removed 2026-09-20 in
favor of the sliders - user request, once the routine became a runtime-adjustable N-tier
chain instead of a fixed 2-tier one, the thing worth surfacing here is "how far should this go"
rather than a raw inventory dump.

Lifecycle (user-specified, 2026-09-18):
- Opens automatically alongside the routine (gather_panel.py creates+shows it when the
  routine starts) as a separate top-level window from the main 마비노비 window, so it can be
  dragged to wherever's convenient while watching the game.
- If the routine auto-stops itself (`blocked` - e.g. an unexpected popup), the window stays
  open but swaps its content for a red "루틴이 중단되었습니다" alert - the queue bars stop
  updating, since they're no longer live and would just be stale.
- If the user manually stops the routine (the button in the main window), this window closes
  itself entirely instead.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox, QLabel, QProgressBar, QVBoxLayout, QWidget

from .altering_routine import FAMILIES, QUEUE_CAPACITY, AlteringRoutineWorker
from .tier_target_control import TierTargetControl


class RoutineDashboard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("가공 무한 대시보드")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.resize(320, 480)

        self._blocked = False
        self._queue_bar: dict[str, QProgressBar] = {}
        self._queue_label: dict[str, QLabel] = {}
        self._controls: dict[str, TierTargetControl] = {}
        self._target_worker: AlteringRoutineWorker | None = None

        outer = QVBoxLayout(self)

        self._alert = QLabel("")
        self._alert.setWordWrap(True)
        self._alert.setStyleSheet("color: #ff5555; font-weight: 700; font-size: 13px; padding: 8px;")
        self._alert.hide()
        outer.addWidget(self._alert)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        targets_box = QGroupBox("목표 등급 설정")
        targets_layout = QVBoxLayout(targets_box)
        for family in FAMILIES:
            control = TierTargetControl(family)
            control.target_changed.connect(self._on_target_changed(family.key))
            targets_layout.addWidget(control)
            self._controls[family.key] = control
        content_layout.addWidget(targets_box, 1)

        queue_box = QGroupBox("가공 시설 대기열")
        queue_layout = QVBoxLayout(queue_box)
        for family in FAMILIES:
            label = QLabel(f"{family.label} ({family.facility}): -/{QUEUE_CAPACITY}")
            bar = QProgressBar()
            bar.setRange(0, QUEUE_CAPACITY)
            bar.setTextVisible(False)
            queue_layout.addWidget(label)
            queue_layout.addWidget(bar)
            self._queue_label[family.key] = label
            self._queue_bar[family.key] = bar
        content_layout.addWidget(queue_box)

        outer.addWidget(self._content, 1)

    def attach(self, worker: AlteringRoutineWorker) -> None:
        worker.snapshot.connect(self._on_snapshot)
        worker.blocked.connect(self._on_blocked)
        worker.stopped.connect(self._on_stopped)
        self.wire_targets(worker)

    def wire_targets(self, worker: AlteringRoutineWorker) -> None:
        """Point the sliders at `worker` - safe to call again for a new worker instance (e.g.
        every time the "가공무한 1시간" JOB restarts against the long-lived embedded dashboard
        in modern_window.py): pushes the sliders' current values into it once immediately, and
        re-targets future drags there instead of whatever worker was previously wired."""
        self._target_worker = worker
        for family_key, control in self._controls.items():
            worker.set_target(family_key, control.value())

    def _on_target_changed(self, family_key: str):
        def handler(idx: int) -> None:
            if self._target_worker is not None:
                self._target_worker.set_target(family_key, idx)
        return handler

    def _on_snapshot(self, snap: dict) -> None:
        if self._blocked:
            return
        queue = snap.get("queue", {})
        queue_completed = snap.get("queue_completed", {})
        for key, n in queue.items():
            bar = self._queue_bar.get(key)
            label = self._queue_label.get(key)
            if bar is None or label is None:
                continue
            bar.setValue(n)
            done = queue_completed.get(key, 0)
            family = next(f for f in FAMILIES if f.key == key)
            text = f"{family.label} ({family.facility}): {n}/{QUEUE_CAPACITY}"
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
