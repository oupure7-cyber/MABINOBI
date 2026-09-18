"""Main dashboard: read-only live views over the game state, built on direct
MabinogiMobile_CLI.exe calls (see app/cli_client.py). No menu bar, no onboarding wizard
on launch - the app tries to connect on its own and only asks for help if that fails.
Scheduled/conditional automation (F1-F4 in 00_SPEC/03_requirements.md) is not implemented
yet - this is the "see what's going on" half of the control app.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
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
from ..updater import apply_update_and_relaunch
from ..version import APP_VERSION
from .connection import ConnectionCheckWorker
from .connector_guide import ConnectorGuideDialog
from .gather_panel import GatherPanel
from .guide_viewer import GuideDialog
from .job_queue import JobQueuePanel
from .music_panel import MusicPanel
from .update_worker import UpdateCheckWorker
from .widgets import CurrencyColumn, Toast, ToggleSwitch

# How often to recheck whether it's safe (nothing running) to apply a downloaded update.
UPDATE_APPLY_RECHECK_MS = 5000

# get_my_info field -> grid position (row, col), 4 columns x 3 rows, user-picked subset
# (see get_my_info in 10_RESEARCH/03_cli_command_reference_2026-09-17.md for the full field list)
TOP_STATS_LAYOUT = [
    ["CombatScore", "LivingScore", "AttractivenessScore", "ArcaneResistance"],
    ["AttackPower", "HealthMax", "DefencePower", "DecorScore"],
    ["STR", "DEX", "INT", "LUCK"],
]

# Emoji stand-in for each stat (user call, 2026-09-19 - tried cropped icons from a screenshot
# first, decided plain emoji was simpler/good enough and dropped the crops).
STAT_EMOJI = {
    "CombatScore": "🏆",
    "LivingScore": "🌿",
    "AttractivenessScore": "💖",
    "ArcaneResistance": "🔮",
    "AttackPower": "🗡️",
    "HealthMax": "❤️",
    "DefencePower": "🛡️",
    "DecorScore": "👑",
    "STR": "👊",
    "DEX": "🤚",
    "INT": "🧠",
    "LUCK": "🍀",
}
STAT_ICON_SIZE = 22


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
                text_col = QVBoxLayout()
                text_col.setSpacing(0)
                text_col.addWidget(name_label)
                text_col.addWidget(value_label)

                cell = QHBoxLayout()
                cell.setSpacing(6)
                cell.addWidget(self._make_stat_icon(key))
                cell.addLayout(text_col)
                self._grid.addLayout(cell, row, col)
                self._cells[key] = (name_label, value_label)

    @staticmethod
    def _make_stat_icon(key: str) -> QLabel:
        icon_label = QLabel(STAT_EMOJI.get(key, ""))
        icon_label.setFixedSize(STAT_ICON_SIZE, STAT_ICON_SIZE)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 15px;")
        return icon_label

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

        self._update_worker: UpdateCheckWorker | None = None
        self._pending_update_exe: Path | None = None
        self._pending_update_version: str | None = None
        self._update_apply_timer: QTimer | None = None

        central = QWidget()
        outer = QVBoxLayout(central)

        outer.addLayout(self._build_control_bar())
        outer.addLayout(self._build_content_row(), 1)

        self.setCentralWidget(central)
        self.toast = Toast(self)

        self._try_connect()
        self._start_update_check()

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

    # -- silent self-update (GitHub Releases, 2026-09-19) ---------------------------

    def _start_update_check(self) -> None:
        # Only the built exe can replace itself this way; a `python main.py` dev run has
        # no "own exe" to swap, and would just overwrite whatever .py-launching wrapper
        # happens to be at sys.executable (python.exe itself) - skip entirely.
        if not getattr(sys, "frozen", False):
            return
        self._update_worker = UpdateCheckWorker(Path(sys.executable), APP_VERSION)
        self._update_worker.update_ready.connect(self._on_update_ready)
        self._update_worker.start()

    def _on_update_ready(self, new_exe_path: str, version: str) -> None:
        self._pending_update_exe = Path(new_exe_path)
        self._pending_update_version = version
        self._update_apply_timer = QTimer(self)
        self._update_apply_timer.setInterval(UPDATE_APPLY_RECHECK_MS)
        self._update_apply_timer.timeout.connect(self._maybe_apply_update)
        self._update_apply_timer.start()

    def _maybe_apply_update(self) -> None:
        # Never interrupt a running 가공 무한 routine or JOB 대기열 - wait until both are
        # idle before swapping the exe out from under the user.
        if self.gather_panel.is_busy() or self.job_queue_panel.is_running():
            return
        self._update_apply_timer.stop()
        self.toast.show_message(f"🔄 새 버전({self._pending_update_version})으로 업데이트합니다...", 2500)
        QTimer.singleShot(2000, self._apply_update_now)

    def _apply_update_now(self) -> None:
        apply_update_and_relaunch(self._pending_update_exe, Path(sys.executable))
        QApplication.instance().quit()
