import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from app.dashboard.modern_window import DashboardWindow
from app.dashboard.ui_kit import OWNED_COUNT_COLOR
from app.dashboard.job_drag import JOB_MIME


def snapshot():
    return {'inventory': [{'DisplayName': '나뭇가지', 'Count': 1234}],
            'character_storage': [{'DisplayName': '나뭇가지', 'Count': 6}],
            'account_storage': [{'DisplayName': '나뭇가지', 'Count': 11}]}


class OwnedUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.window = DashboardWindow(root, connect_on_start=False,
                                      settings=QSettings(str(root/'ui.ini'), QSettings.IniFormat))

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def values(self, row=0):
        return [self.window.catalog.item(row, c).text() for c in self.window._owned_columns]

    def test_unknown_zero_and_warehouse_breakdown(self):
        w = self.window
        w.search.setText('나뭇가지')
        row = next(r for r in range(w.catalog.rowCount()) if w.catalog.item(r,0).text() == '나뭇가지')
        self.assertEqual(self.values(row), ['—', '—', '—'])
        w.apply_owned_inventory(snapshot())
        self.assertEqual(self.values(row), ['1,234', '17', '1,251'])
        tooltip = w.catalog.item(row, w._owned_columns[1]).toolTip()
        self.assertIn('캐릭터 창고: 6개', tooltip)
        self.assertIn('계정 창고: 11개', tooltip)
        w.apply_owned_inventory({'inventory': [], 'character_storage': [], 'account_storage': []})
        self.assertEqual(self.values(row), ['0', '0', '0'])
        w.apply_owned_inventory(None)
        self.assertEqual(self.values(row), ['—', '—', '—'])

    def test_selected_cells_remain_yellow_and_can_drag(self):
        w = self.window
        w.search.setText('나뭇가지')
        w.apply_owned_inventory(snapshot())
        w.catalog.selectRow(0)
        column = w._owned_columns[0]
        option = QStyleOptionViewItem()
        w.catalog.itemDelegate().initStyleOption(option, w.catalog.model().index(0,column))
        self.assertEqual(option.palette.color(QPalette.HighlightedText).name(), OWNED_COUNT_COLOR)
        mime = w.catalog.mimeData([w.catalog.item(0,column)])
        self.assertEqual(bytes(mime.data(JOB_MIME)).decode(), w.catalog.item(0,0).data(Qt.UserRole))

    def test_refresh_preserves_recipe_editor_selection_and_scroll(self):
        w = self.window
        w.select_category('제작')
        w.show()
        self.app.processEvents()
        w.catalog.selectRow(4)
        editor = w.catalog.cellWidget(4,1)
        editor.setValue(137)
        w.catalog.verticalScrollBar().setValue(3)
        old_scroll = w.catalog.verticalScrollBar().value()
        w.apply_owned_inventory(snapshot())
        self.assertIs(w.catalog.cellWidget(4,1), editor)
        self.assertEqual(editor.value(),137)
        self.assertEqual(w.catalog.currentRow(),4)
        self.assertEqual(w.catalog.verticalScrollBar().value(),old_scroll)

    def test_category_changes_and_equipment_unavailable(self):
        w = self.window
        w.apply_owned_inventory(snapshot())
        w.select_category('요리')
        self.assertEqual(w.catalog.columnCount(),5)
        w.select_category('제작')
        w.search.setText('크레센트 엣지소드')
        self.assertEqual(self.values(), ['—', '—', '—'])
        self.assertIn('장비 보유 수량',w.catalog.item(0,w._owned_columns[0]).toolTip())
        w.search.clear()
        w.select_category('무한가공소')
        self.assertEqual(w.catalog.columnCount(),2)
        self.assertEqual(w._owned_columns,())

    def test_stale_status_distinguishes_last_known_from_current(self):
        w = self.window
        w.apply_owned_inventory(snapshot())
        w._owned_checked_at -= 20
        w.refresh_owned_status()
        self.assertIn('최근 확인',w.owned_status.text())
        self.assertIn('재조회 대기',w.owned_status.text())


if __name__ == '__main__':
    unittest.main()
