"""Entry point for 마비노비 (MabiNobi), the Mabinogi AI 자동화 제어 앱.

Goes straight to the dashboard (app/dashboard/main_window.py), which tries to connect to
the game on its own at startup.

    python 50_APP/main.py

Also the entry point PyInstaller builds the standalone 마비노비.exe from directly (2026-09-19
- the whole app + its assets get bundled into one file, so end users need nothing but the
exe: no system Python, no project folder alongside it). PROJECT_ROOT has to account for both
cases: when frozen, __file__ doesn't point anywhere meaningful on disk (PyInstaller extracts
into a temp dir), so it's derived from sys.executable's own location (wherever the user put
the exe) instead. 그 project_root는 "사용 가이드" 버튼(10_RESEARCH 참조) 전용이라, 순수 단독
exe로 배포된 경우 그 폴더가 없으면 해당 버튼만 "못 찾음"으로 우아하게 실패한다 - 대시보드 핵심
기능(스탯/재화/가공 무한/JOB 대기열/음악)엔 영향 없음.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.dashboard.main_window import DashboardWindow

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent


def apply_dark_theme(app: QApplication) -> None:
    """Keep every app window dark, independently of the Windows theme."""
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    app.setStyle("Fusion")
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#202024",
        QPalette.ColorRole.WindowText: "#eeeeee",
        QPalette.ColorRole.Base: "#18181c",
        QPalette.ColorRole.AlternateBase: "#2b2b30",
        QPalette.ColorRole.Text: "#eeeeee",
        QPalette.ColorRole.Button: "#303036",
        QPalette.ColorRole.ButtonText: "#eeeeee",
        QPalette.ColorRole.ToolTipBase: "#303036",
        QPalette.ColorRole.ToolTipText: "#eeeeee",
        QPalette.ColorRole.PlaceholderText: "#99999f",
        QPalette.ColorRole.Highlight: "#446b9e",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Link: "#80bfff",
        QPalette.ColorRole.LinkVisited: "#c5a3ff",
        QPalette.ColorRole.Light: "#505056",
        QPalette.ColorRole.Midlight: "#404046",
        QPalette.ColorRole.Mid: "#303036",
        QPalette.ColorRole.Dark: "#141418",
        QPalette.ColorRole.Shadow: "#101014",
        QPalette.ColorRole.Accent: "#80bfff",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#85858b"))
    app.setPalette(palette)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("마비노비")
    apply_dark_theme(app)

    dashboard = DashboardWindow(PROJECT_ROOT)
    dashboard.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
