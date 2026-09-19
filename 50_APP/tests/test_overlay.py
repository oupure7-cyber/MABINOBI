"""Run: python -m unittest discover -s tests (no game CLI calls).

Most of overlay.py is inherently OS/Qt-window integration (finding the real game window
via ctypes, click-through window flags) that's more meaningfully verified live against
the actual running game than mocked - see CHANGELOG 2026-09-20 for that verification.
These tests cover what's reasonably testable offscreen without a live game: panel
structure and the facility-name shortening, independent of any CLI/window state.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app.dashboard.altering_routine import CHAINS
from app.dashboard.overlay import (
    OVERLAY_BACKGROUND_OPACITY_PERCENT, EnvironmentOverlay, FacilityOverlay, OverlayManager,
)


class OverlayStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_facility_overlay_has_one_row_per_altering_chain(self):
        panel = FacilityOverlay()
        self.assertEqual(set(panel._rows), {chain.facility for chain in CHAINS})

    def test_facility_short_labels_drop_the_facility_suffix(self):
        panel = FacilityOverlay()
        for chain in CHAINS:
            short, _label = panel._rows[chain.facility]
            self.assertNotIn('시설', short)
            self.assertTrue(chain.facility.startswith(short))

    def test_facility_rows_start_with_a_placeholder_before_any_data(self):
        panel = FacilityOverlay()
        for _short, label in panel._rows.values():
            self.assertIn('-/7', label.text())

    def test_environment_overlay_starts_with_a_placeholder(self):
        panel = EnvironmentOverlay()
        self.assertEqual(panel._label.text(), '-')

    def test_click_through_and_always_on_top_flags_are_set(self):
        from PySide6.QtCore import Qt
        panel = FacilityOverlay()
        self.assertTrue(panel.windowFlags() & Qt.WindowTransparentForInput)
        self.assertTrue(panel.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertTrue(panel.testAttribute(Qt.WA_TranslucentBackground))

    def test_opacity_constant_is_a_valid_percentage(self):
        self.assertGreater(OVERLAY_BACKGROUND_OPACITY_PERCENT, 0)
        self.assertLessEqual(OVERLAY_BACKGROUND_OPACITY_PERCENT, 100)

    def test_manager_owns_exactly_the_facility_and_environment_panels(self):
        mgr = OverlayManager()
        self.assertEqual(len(mgr.panels), 2)
        self.assertTrue(any(isinstance(p, FacilityOverlay) for p in mgr.panels))
        self.assertTrue(any(isinstance(p, EnvironmentOverlay) for p in mgr.panels))

    def test_disabled_by_default(self):
        mgr = OverlayManager()
        self.assertFalse(mgr._enabled)
        self.assertFalse(mgr._timer.isActive())


if __name__ == '__main__':
    unittest.main()
