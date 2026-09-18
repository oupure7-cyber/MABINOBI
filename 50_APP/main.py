"""Entry point for 마비노비 (MabiNobi), the Mabinogi AI 자동화 제어 앱.

Goes straight to the dashboard (app/dashboard/main_window.py), which tries to connect to
the game on its own at startup. The onboarding wizard (app/onboarding/wizard.py) is only
opened on demand, from the dashboard's "설치 마법사" button.

    python 50_APP/main.py
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.dashboard.main_window import DashboardWindow

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("마비노비")

    dashboard = DashboardWindow(PROJECT_ROOT)
    dashboard.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
