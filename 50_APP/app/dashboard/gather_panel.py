"""Center panel: the "가공 무한" infinite routine toggle + its status readout.

The one-click quick-gather button grid that used to live here (25 items, 단단한 통나무 등) was
removed 2026-09-18 once the JOB queue existed - each of those buttons is now a one-shot JOB
in job_queue.py's catalog instead (gather_job.py's GatherJobWorker, named "채집: <이름> x100"),
searchable/queueable/repeatable there rather than a fixed always-visible grid. This panel now
only hosts the "가공 무한" (강철괴/목재+/옷감+/가죽+) toggle button - see altering_routine.py.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from .altering_routine import AlteringRoutineWorker
from .routine_dashboard import RoutineDashboard

STEEL_BTN_IDLE_TEXT = "🔁 가공 무한 시작 (강철괴/목재+/옷감+/가죽+)"
STEEL_HINT_TEXT = "⚠️ 티르코네일+숲길잡이+흰까마귀+검술로 세팅해두면 효율이 더 높아요!"


class GatherPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._steel_worker: AlteringRoutineWorker | None = None
        self._routine_dashboard: RoutineDashboard | None = None
        self._job_queue_panel = None  # set via set_job_queue_panel() - avoids a circular import

        outer = QVBoxLayout(self)

        hint = QLabel(STEEL_HINT_TEXT)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #e0a030; font-size: 11px; font-weight: 600;")
        outer.addWidget(hint)

        self._steel_btn = QPushButton(STEEL_BTN_IDLE_TEXT)
        self._steel_btn.setStyleSheet(
            "QPushButton { background-color: #3a2f1a; color: #f0c060; font-weight: 600; padding: 6px; }"
        )
        self._steel_btn.clicked.connect(self._toggle_steel_routine)
        outer.addWidget(self._steel_btn)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #ddd; font-size: 11px; padding: 2px 0;")
        outer.addWidget(self._status_label)

        outer.addStretch(1)

    def set_job_queue_panel(self, panel) -> None:
        self._job_queue_panel = panel

    def is_busy(self) -> bool:
        """Whether this panel currently has a worker calling the CLI - JobQueuePanel checks
        this before starting a JOB, same one-caller-at-a-time constraint as everywhere else."""
        return self._steel_worker is not None

    # -- 가공 무한 routine (강철괴/목재+/옷감+/가죽+) ------------------------

    def _toggle_steel_routine(self) -> None:
        if self._steel_worker is not None:
            self._steel_btn.setEnabled(False)
            self._steel_btn.setText("정지 중...")
            self._steel_worker.request_stop()
            return

        if self._job_queue_panel is not None and self._job_queue_panel.is_running():
            self._status_label.setText("JOB 대기열이 실행 중입니다. 완료 후 다시 시도해주세요.")
            return

        self._steel_btn.setText("⏹ 가공 무한 정지")
        self._status_label.setText("가공 무한 루틴 시작...")

        worker = AlteringRoutineWorker(self)
        worker.status.connect(self._on_steel_status)
        worker.blocked.connect(self._on_steel_blocked)
        worker.stopped.connect(self._on_steel_stopped)
        self._steel_worker = worker

        # Standalone window, not a child dialog of the main 마비노비 window - the user drags it
        # wherever's convenient while watching the game. It listens to the worker's `snapshot`
        # signal only (never calls the CLI itself) and manages its own lifecycle from there:
        # stays open with a red alert if the routine auto-stops (`blocked`), closes itself if
        # the routine was stopped manually (this button) instead.
        dashboard = RoutineDashboard(self.window())
        dashboard.attach(worker)
        dashboard.destroyed.connect(self._on_dashboard_destroyed)
        self._routine_dashboard = dashboard
        dashboard.show()

        worker.start()

    def _on_steel_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _on_steel_blocked(self, kind: str) -> None:
        self._status_label.setText(f"⚠️ 게임에서 확인이 필요해 가공 무한 루틴을 멈췄습니다: {kind}")

    def _on_steel_stopped(self) -> None:
        self._steel_worker = None
        self._steel_btn.setEnabled(True)
        self._steel_btn.setText(STEEL_BTN_IDLE_TEXT)

    def _on_dashboard_destroyed(self, *_args) -> None:
        self._routine_dashboard = None
