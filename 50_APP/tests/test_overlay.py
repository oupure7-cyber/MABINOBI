import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from app.dashboard.progress_overlay import ProgressOverlay, SCALE

class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.settings = {}
        self.overlay = ProgressOverlay(self.settings)
        self.overlay._timer.stop()
    def tearDown(self):
        self.overlay.close()
        self.overlay.deleteLater()
        self.app.processEvents()
    def test_game_only_and_preview_visibility_toggle(self):
        with patch.object(self.overlay._game, 'rectangle', return_value=None):
            self.overlay.set_progress({'recipe': '강철괴', 'target': 3})
            self.assertFalse(self.overlay.isVisible())
            self.overlay.set_preview(True)
            self.assertTrue(self.overlay.isVisible())
            self.overlay.set_enabled(False)
            self.assertFalse(self.overlay.isVisible())
            self.assertFalse(self.settings['overlay/enabled'])
    def test_80_percent_size_regular_font_transparent_corners(self):
        self.assertEqual(SCALE, .8)
        self.assertEqual((self.overlay.width(), self.overlay.height()), (240, 264))
        self.overlay.set_preview(True)
        self.overlay.set_progress({'recipe': '강철괴', 'completed': 1, 'target': 3, 'stage': '재료 준비',
            'materials': [{'name': '철괴', 'owned': 2, 'required': 6, 'state': '가공 중', 'remaining_seconds': 90}]})
        image = QImage(self.overlay.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        self.overlay.render(image)
        for x, y in [(0, 0), (239, 0), (239, 263), (0, 263), (100, 240)]:
            self.assertEqual(image.pixelColor(x, y).alpha(), 0, (x, y))
        self.assertTrue(any(image.pixelColor(x, 40).alpha() for x in range(35, 230)))
    def test_unlock_temporarily_allows_drag_without_losing_preference(self):
        self.assertTrue(self.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.overlay.set_locked(False)
        self.assertFalse(self.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.assertTrue(self.overlay.click_through)
        self.overlay.set_locked(True)
        self.assertTrue(self.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        self.overlay.set_opacity(.45)
        self.assertEqual(self.settings['overlay/opacity'], .45)
        self.assertTrue(self.overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)

if __name__ == '__main__': unittest.main()
