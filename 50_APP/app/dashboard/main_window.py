"""Main dashboard: read-only live views over the game state, built on direct
MabinogiMobile_CLI.exe calls (see app/cli_client.py). No menu bar, no onboarding wizard
on launch - the app tries to connect on its own and only asks for help if that fails.
Scheduled/conditional automation (F1-F4 in 00_SPEC/03_requirements.md) is not implemented
yet - this is the "see what's going on" half of the control app.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..cli_client import run_cli
from ..onboarding.wizard import OnboardingWizard
from .connection import ConnectionCheckWorker
from .connector_guide import ConnectorGuideDialog
from .gather_panel import GatherPanel
from .guide_viewer import GuideDialog
from .job_queue import JobQueuePanel
from .music_panel import MusicPanel
from .widgets import CurrencyColumn, Toast, ToggleSwitch

# get_my_info field -> grid position (row, col), 4 columns x 3 rows, user-picked subset
# (see get_my_info in 10_RESEARCH/03_cli_command_reference_2026-09-17.md for the full field list)
TOP_STATS_LAYOUT = [
    ["CombatScore", "LivingScore", "AttractivenessScore", "ArcaneResistance"],
    ["AttackPower", "HealthMax", "DefencePower", "DecorScore"],
    ["STR", "DEX", "INT", "LUCK"],
]


class TopStatsPanel(QWidget):
    """Fixed 4x3 grid of hand-picked get_my_info stats, shown top-left of the window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: #e0a030;")
        self._error_label.hide()
        outer.addWidget(self._error_label)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(20)
        self._grid.setVerticalSpacing(4)
        outer.addLayout(self._grid)

        self._cells: dict[str, tuple[QLabel, QLabel]] = {}
        for row, keys in enumerate(TOP_STATS_LAYOUT):
            for col, key in enumerate(keys):
                name_label = QLabel(key)
                name_label.setStyleSheet("color: #9a9aa2; font-size: 10px;")
                value_label = QLabel("-")
                value_label.setStyleSheet("color: #f0f0f0; font-size: 13px; font-weight: 600;")
                cell = QVBoxLayout()
                cell.setSpacing(0)
                cell.addWidget(name_label)
                cell.addWidget(value_label)
                self._grid.addLayout(cell, row, col)
                self._cells[key] = (name_label, value_label)

    def set_data(self, data) -> None:
        if not isinstance(data, dict) or "error" in data:
            message = data.get("message", data.get("error")) if isinstance(data, dict) else str(data)
            self._error_label.setText(f"⚠️ {message}")
            self._error_label.show()
            return
        self._error_label.hide()

        for key, (name_label, value_label) in self._cells.items():
            entry = data.get(key)
            if not isinstance(entry, dict):
                name_label.setText(key)
                value_label.setText("-")
                continue
            name_label.setText(str(entry.get("DisplayName", key)))
            value = entry.get("Value")
            value_label.setText(f"{value:,}" if isinstance(value, int) else str(value))


class DashboardWindow(QMainWindow):
    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        self.setWindowTitle("마비노비")
        self.resize(1450, 750)  # widened for the JOB 대기열 right column (2026-09-18)

        self._connection_worker: ConnectionCheckWorker | None = None
        self._guide_dialog: ConnectorGuideDialog | None = None

        central = QWidget()
        outer = QVBoxLayout(central)

        outer.addLayout(self._build_control_bar())
        outer.addLayout(self._build_content_row(), 1)

        self.setCentralWidget(central)
        self.toast = Toast(self)

        self._try_connect()

    # -- layout builders --------------------------------------------------

    def _build_control_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()

        self.top_stats = TopStatsPanel()
        bar.addWidget(self.top_stats)

        bar.addStretch(1)

        bar.addWidget(QLabel("MCP 연결"))
        self.connection_toggle = ToggleSwitch()
        self.connection_toggle.toggled.connect(self._on_toggle)
        bar.addWidget(self.connection_toggle)

        wizard_btn = QPushButton("설치 마법사")
        wizard_btn.clicked.connect(self.open_wizard)
        bar.addWidget(wizard_btn)

        guide_btn = QPushButton("사용 가이드")
        guide_btn.clicked.connect(self.open_guide)
        bar.addWidget(guide_btn)
        return bar

    def _build_content_row(self) -> QHBoxLayout:
        row = QHBoxLayout()

        self.currency_column = CurrencyColumn()
        row.addWidget(self.currency_column)

        center_split = QSplitter(Qt.Vertical)
        self.gather_panel = GatherPanel()
        self.music_panel = MusicPanel()
        center_split.addWidget(self.gather_panel)
        center_split.addWidget(self.music_panel)
        row.addWidget(center_split, 1)

        self.job_queue_panel = JobQueuePanel()
        self.job_queue_panel.setFixedWidth(320)
        self.job_queue_panel.set_gather_panel(self.gather_panel)
        self.gather_panel.set_job_queue_panel(self.job_queue_panel)
        row.addWidget(self.job_queue_panel)

        return row

    # -- connection ----------------------------------------------------------

    def open_wizard(self) -> None:
        wizard = OnboardingWizard(self.project_root, self)
        wizard.exec()
        self._try_connect()

    def open_guide(self) -> None:
        GuideDialog(self.project_root, self).exec()

    def _on_toggle(self, checked: bool) -> None:
        if checked:
            self._try_connect()

    def _try_connect(self) -> None:
        if self._connection_worker is not None and self._connection_worker.isRunning():
            return
        self._connection_worker = ConnectionCheckWorker()
        self._connection_worker.result.connect(self._on_connection_result)
        self._connection_worker.start()

    def _on_connection_result(self, ok: bool, _detail: str) -> None:
        self.connection_toggle.blockSignals(True)
        self.connection_toggle.setChecked(ok)
        self.connection_toggle.blockSignals(False)

        if ok:
            self.toast.show_message("게임과 연결됐어요", 2000)
            self.refresh_all()
        else:
            self._show_guide_popup()

    def _show_guide_popup(self) -> None:
        if self._guide_dialog is not None and self._guide_dialog.isVisible():
            return
        self._guide_dialog = ConnectorGuideDialog(self)
        self._guide_dialog.show()

    # -- data refresh ----------------------------------------------------------

    def refresh_all(self) -> None:
        self.top_stats.set_data(run_cli("get_my_info"))
        self.currency_column.set_data(run_cli("get_currencies"))
        self.music_panel.refresh_songs()
