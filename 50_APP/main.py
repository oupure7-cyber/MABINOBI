"""Entry point for 마비노비 (MabiNobi), the Mabinogi AI 자동화 제어 앱.

Goes straight to the dashboard (app/dashboard/modern_window.py), which tries to connect to
the game on its own at startup.

    python 50_APP/main.py

Also the entry point PyInstaller builds the standalone 마비노비.exe from directly (2026-09-19
- the whole app + its assets get bundled into one file, so end users need nothing but the
exe: no system Python, no project folder alongside it). PROJECT_ROOT has to account for both
cases: when frozen, __file__ doesn't point anywhere meaningful on disk (PyInstaller extracts
into a temp dir), so it's derived from sys.executable's own location (wherever the user put
the exe) instead - it's also where character_data/와 cli_settings.json이 exe와 나란히 저장돼서,
자동 업데이트로 exe 파일만 교체돼도(app/updater.py) 그대로 남는다.

ensure_cli_path()가 시작 시 MabinogiMobile_CLI.exe를 못 찾으면 설치 폴더를 직접 고르게 하고
그 경로를 저장한다(app/dashboard/cli_setup.py) - 넥슨 기본 경로에 설치하지 않은 사용자 대응.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.dashboard.modern_window import DashboardWindow
from app.dashboard.cli_setup import ensure_cli_path
from app.version import APP_VERSION

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

    self_test = '--ui-self-test' in sys.argv
    output = Path(sys.argv[sys.argv.index('--ui-self-test') + 1]) if self_test else None
    test_settings = QSettings(str(output.with_suffix('.ini')), QSettings.IniFormat) if self_test else None
    if not self_test:
        ensure_cli_path(PROJECT_ROOT)
    dashboard = DashboardWindow(PROJECT_ROOT, connect_on_start=not self_test, settings=test_settings)
    dashboard.show()

    if self_test:
        # Exercise the frozen Qt runtime and real window, without contacting the game.
        def report_ready():
            import json
            output.write_text(json.dumps({
                'version': APP_VERSION,
                'visible': dashboard.isVisible(),
                'title': dashboard.windowTitle(),
                'tabs': [dashboard.tabs.tabText(i) for i in range(dashboard.tabs.count())],
                  'catalog_rows': dashboard.catalog.rowCount(),
                  'catalog_columns': dashboard.catalog.columnCount(),
                  'catalog_icons': sum(not dashboard.catalog.item(i, 0).icon().isNull() for i in range(dashboard.catalog.rowCount())),
                  'catalog_drag_enabled': dashboard.catalog.dragEnabled(),
                  'queue_accepts_drops': dashboard.queue.list.acceptDrops(),
            }, ensure_ascii=False), encoding='utf-8')
            dashboard.grab().save(str(output.with_suffix('.png')))
            dashboard.select_category('요리')
            app.processEvents()
            dashboard.grab().save(str(output.with_name(output.stem + '-cooking.png')))
            output.with_name(output.stem + '-cooking.json').write_text(json.dumps({
                'rows': dashboard.catalog.rowCount(),
                'names': [dashboard.catalog.item(i, 0).text() for i in range(dashboard.catalog.rowCount())],
            }, ensure_ascii=False), encoding='utf-8')
            dashboard.select_category('제작')
            app.processEvents()
            dashboard.grab().save(str(output.with_name(output.stem + '-equipment.png')))
            output.with_name(output.stem + '-equipment.json').write_text(json.dumps({
                'rows': dashboard.catalog.rowCount(),
                'names': [dashboard.catalog.item(i, 0).text() for i in range(dashboard.catalog.rowCount())],
            }, ensure_ascii=False), encoding='utf-8')
            dashboard.select_category('무한가공소')
            app.processEvents()
            dashboard.grab().save(str(output.with_name(output.stem + '-workshop.png')))
            dashboard.overlay.set_enabled(True)
            dashboard.overlay.set_progress({'recipe':'무한가공소', 'stage':'가공', 'materials':[
                {'name':name,'owned':done,'required':7,'state':f'시설 7/7 · 완료 {done}'}
                for name,done in [('강철괴',2),('목재+',4),('옷감+',0),('가죽+',7)]], 'message':'화면 검증용 예시 · 실제 게임 데이터 아님'})
            dashboard.overlay.set_preview(True)
            app.processEvents()
            dashboard.overlay.grab().save(str(output.with_name(output.stem + '-overlay.png')))
            dashboard.close()
            app.quit()
        QTimer.singleShot(800, report_ready)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
