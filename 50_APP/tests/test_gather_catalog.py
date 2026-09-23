import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys, json, unittest, tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from app.dashboard.gather_catalog import parse_gather_items, gather_state
from app.dashboard.gather_job import GATHER_ITEMS, GatherJobWorker
from app.dashboard.item_icons import item_icon
from app.dashboard.modern_window import DashboardWindow


class GatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def test_catalog_and_real_images(self):
        self.assertEqual(len(GATHER_ITEMS), 128)
        for name in ('밀', '물이 든 병', '최상급 통나무+', '황금 양털+', '푸른 진색초 꽃잎'):
            self.assertIn(name, GATHER_ITEMS)
        for name in GATHER_ITEMS:
            self.assertFalse(item_icon(name).pixmap(32,32).isNull(), name)
        for name in ('목재', '생가죽', '새록 버섯 포자', '농어', '버터'):
            self.assertNotIn(name, GATHER_ITEMS)

    def test_api_validation_and_fishing(self):
        rows = parse_gather_items({'status':'accepted','body':{'items':[{'DisplayName':'밀','ToolOk':False},{'DisplayName':'농어','ToolOk':True}]}})
        self.assertEqual(set(rows), {'밀'})
        self.assertEqual(gather_state('밀', rows), '도구 확인 필요')
        self.assertEqual(gather_state('쌀', rows), '현재 목록에 없음')
        self.assertEqual(parse_gather_items({'items':[]}), {})
        for data in ({'pipe':'disconnected'}, {'items':[{}]}, {'error':'failed'}, {}):
            with self.assertRaises(ValueError): parse_gather_items(data)

    def test_ui_search_sync_and_exact_queue_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            window = DashboardWindow(Path(tmp), connect_on_start=False, settings=QSettings(str(Path(tmp)/'test.ini'),QSettings.IniFormat))
            self.assertEqual(window.catalog.rowCount(),128)
            window.apply_gathering({'items':[{'DisplayName':'밀','ToolOk':True},{'DisplayName':'새 채집 재료','ToolOk':True}]})
            self.assertEqual(window.catalog.rowCount(),129)
            window.apply_gathering({'items':[{'DisplayName':'밀','ToolOk':False}]})
            self.assertEqual(window.catalog.rowCount(),129)
            window.search.setText('밀')
            self.assertEqual(window.catalog.rowCount(),1)
            window.add_job_key('gather_밀')
            self.assertEqual(len(window.queue.jobs),1)
            self.assertIsNone(window.queue.worker)
            with patch('app.dashboard.gather_job.run_cli',return_value={'status':'accepted'}) as cli:
                GatherJobWorker('황금 거미줄+').run()
                self.assertEqual(json.loads(cli.call_args.args[1]),{'displayName':'황금 거미줄+'})
            window.close()

if __name__ == '__main__': unittest.main()
