"""Center panel: one-click gathering shortcuts. Replaces the earlier free-text chat console -
clicking a button IS the confirmation (no extra dialog), matching how the original "황금 개암
버섯" quick-action button worked. Runs execute_gathering off the GUI thread since a full
100-item run can take minutes (see CHANGELOG 2026-09-18, the timeout bug found while testing
황금 개암 버섯 live)."""

from __future__ import annotations

import json

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..cli_client import run_cli
from .altering_routine import AlteringRoutineWorker
from .routine_dashboard import RoutineDashboard
from .widgets import classify_cli_result

GATHER_TIMEOUT = 900  # execute_gathering can take several minutes for a full 100-item run

# User-picked list (2026-09-18), duplicates in the original request collapsed, sorted 가나다순.
GATHER_ITEMS = sorted(
    dict.fromkeys(
        [
            "황금 개암 버섯",
            "황금 달걀",
            "황금 거미줄",
            "황금 네잎클로버",
            "황금 우유",
            "황금 사과",
            "황금 나뭇가지",
            "황금 헤이즐넛",
            "황금 거미줄+",
            "단단한 통나무",
            "황금 풍뎅이",
            "부드러운 통나무",
            "벼락 맞은 나뭇가지",
            "황금 부스러기",
            "마력 깃든 돌",
            "반짝이는 이끼",
            "황금 이끼",
            "황금 양털",
            "두꺼운 양털",
            "황금 양털+",
            "황금 줄기",
            "묵직한 감자",
            "황금 나비",
            "황금 잠자리",
            "황금 사슴벌레",
        ]
    )
)

GRID_COLUMNS = 4


class CliCallWorker(QThread):
    result_ready = Signal(object)

    def __init__(self, command: str, body: str | None, timeout: int, parent=None):
        super().__init__(parent)
        self._command = command
        self._body = body
        self._timeout = timeout

    def run(self) -> None:
        self.result_ready.emit(run_cli(self._command, self._body, timeout=self._timeout))


class GatherPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._gather_worker: CliCallWorker | None = None
        self._steel_worker: AlteringRoutineWorker | None = None
        self._routine_dashboard: RoutineDashboard | None = None
        self._job_queue_panel = None  # set via set_job_queue_panel() - avoids a circular import
        self._buttons: list[QPushButton] = []

        outer = QVBoxLayout(self)

        title = QLabel("채집 바로가기 — 클릭하면 바로 채집을 시작해요 (정령의 날개 5개 소모)")
        title.setWordWrap(True)
        title.setStyleSheet("color: #aaa; font-size: 11px;")
        outer.addWidget(title)

        self._steel_btn = QPushButton("🔁 가공 무한 시작 (강철괴/목재+/옷감+/가죽+) (티르코네일+숲길잡이+흰까마귀+검술)")
        self._steel_btn.setStyleSheet(
            "QPushButton { background-color: #3a2f1a; color: #f0c060; font-weight: 600; padding: 6px; }"
        )
        self._steel_btn.clicked.connect(self._toggle_steel_routine)
        outer.addWidget(self._steel_btn)

        # Status readout lives right under the routine button - not buried below the gather
        # grid - so it's always visible while the routine or a quick-gather click is running,
        # instead of the character seeming to sit there idle with no explanation on screen.
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #ddd; font-size: 11px; padding: 2px 0;")
        outer.addWidget(self._status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        for index, item_name in enumerate(GATHER_ITEMS):
            btn = QPushButton(item_name)
            btn.clicked.connect(lambda _checked=False, name=item_name: self._quick_gather(name))
            grid.addWidget(btn, index // GRID_COLUMNS, index % GRID_COLUMNS)
            self._buttons.append(btn)
        scroll.setWidget(grid_host)
        outer.addWidget(scroll, 1)

    def set_job_queue_panel(self, panel) -> None:
        self._job_queue_panel = panel

    def is_busy(self) -> bool:
        """Whether this panel currently has a worker calling the CLI - JobQueuePanel checks
        this before starting a JOB, same one-caller-at-a-time constraint as everywhere else."""
        return self._gather_worker is not None or self._steel_worker is not None

    def _lookup_gatherable(self, item_name: str) -> dict | None:
        lookup = run_cli("get_gatherable_items", item_name)
        items = lookup.get("items", []) if isinstance(lookup, dict) else []
        match = next((i for i in items if i.get("DisplayName") == item_name), None)
        if match is None and len(items) == 1:
            match = items[0]
        if match is None:
            self._status_label.setText(f"⚠️ '{item_name}'과 일치하는 채집 항목을 찾지 못했습니다.")
        return match

    def _quick_gather(self, item_name: str) -> None:
        if self._gather_worker is not None:
            self._status_label.setText("이미 채집이 진행 중입니다. 완료 후 다시 시도해주세요.")
            return
        if self._steel_worker is not None:
            self._status_label.setText("가공 무한 루틴 실행 중에는 사용할 수 없습니다. 먼저 정지해주세요.")
            return
        if self._job_queue_panel is not None and self._job_queue_panel.is_running():
            self._status_label.setText("JOB 대기열이 실행 중입니다. 완료 후 다시 시도해주세요.")
            return

        match = self._lookup_gatherable(item_name)
        if match is None:
            return

        display_name = match["DisplayName"]
        tool_note = " (⚠️ 도구 부족 가능)" if not match.get("ToolOk", True) else ""
        self._status_label.setText(f"'{display_name}' 채집 시작...{tool_note} 완료까지 몇 분 걸릴 수 있어요.")
        self._set_busy(True)

        body_json = json.dumps({"displayName": display_name}, ensure_ascii=False)
        worker = CliCallWorker("execute_gathering", body_json, GATHER_TIMEOUT, self)
        worker.result_ready.connect(lambda data: self._on_gather_done(display_name, data))
        self._gather_worker = worker
        worker.start()

    def _on_gather_done(self, display_name: str, data) -> None:
        self._gather_worker = None
        self._set_busy(False)

        ok, reason = classify_cli_result(data)
        if ok:
            gained = data.get("gained") if isinstance(data, dict) else None
            detail = f" ({gained}개)" if gained is not None else ""
            self._status_label.setText(f"✅ '{display_name}' 채집 성공{detail}")
            return

        kind = data.get("kind") if isinstance(data, dict) else None
        extra = f" — 게임에서 확인 필요: {kind}" if kind else ""
        self._status_label.setText(f"❌ '{display_name}' 채집 실패: {reason}{extra}")

    def _set_busy(self, busy: bool) -> None:
        for btn in self._buttons:
            btn.setEnabled(not busy)

    # -- 가공 무한 routine (강철괴/목재+/옷감+/가죽+) ------------------------

    def _toggle_steel_routine(self) -> None:
        if self._steel_worker is not None:
            self._steel_btn.setEnabled(False)
            self._steel_btn.setText("정지 중...")
            self._steel_worker.request_stop()
            return

        if self._gather_worker is not None:
            self._status_label.setText("채집이 진행 중입니다. 완료 후 다시 시도해주세요.")
            return
        if self._job_queue_panel is not None and self._job_queue_panel.is_running():
            self._status_label.setText("JOB 대기열이 실행 중입니다. 완료 후 다시 시도해주세요.")
            return

        self._set_busy(True)
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
        self._steel_btn.setText("🔁 가공 무한 시작 (강철괴/목재+/옷감+/가죽+) (티르코네일+숲길잡이+흰까마귀+검술)")
        self._set_busy(False)

    def _on_dashboard_destroyed(self, *_args) -> None:
        self._routine_dashboard = None
