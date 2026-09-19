import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys, unittest, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidgetItem
from app.dashboard.job_drag import JobCatalogTable, JobDropTable, JOB_MIME
from app.dashboard.item_icons import ICON_DIR, item_icon, spec_item_name
from app.dashboard.job_queue import JOB_CATALOG

class Event:
    def __init__(self, source, mime): self.src, self.mime, self.accepted = source, mime, False
    def source(self): return self.src
    def mimeData(self): return self.mime
    def setDropAction(self, action): self.action = action
    def accept(self): self.accepted = True
    def ignore(self): self.accepted = False

class DragIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def test_catalog_drop_and_external_rejection(self):
        source = JobCatalogTable(1, 2)
        item = QTableWidgetItem('황금 양털'); item.setData(Qt.UserRole, 'gather_황금 양털')
        source.setItem(0, 0, item)
        target = JobDropTable(0, 3); added = []
        target.jobDropped.connect(added.append)
        mime = source.mimeData([item])
        event = Event(source, mime); target.dropEvent(event)
        self.assertTrue(event.accepted)
        self.assertEqual(added, ['gather_황금 양털'])
        external = Event(None, mime); target.dropEvent(external)
        self.assertFalse(external.accepted)
        mime.setData(JOB_MIME, b'unknown'); target.dropEvent(Event(source, mime))
        self.assertEqual(len(added), 1)
    def test_exact_icons_decode_and_unknown_has_no_substitute(self):
        manifest = json.loads((ICON_DIR/'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest), 42)
        for name in manifest:
            self.assertFalse(item_icon(name).pixmap(26, 26).isNull(), name)
        for spec in JOB_CATALOG:
            if spec.key.startswith(('gather_', 'veggie_')):
                self.assertFalse(item_icon(spec_item_name(spec)).isNull(), spec.name)
        self.assertTrue(item_icon('황금 양털 비슷한 이름').isNull())

if __name__ == '__main__': unittest.main()
