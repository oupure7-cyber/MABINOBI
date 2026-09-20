"""Run: python -m unittest discover -s tests (no game CLI calls)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app.dashboard.modern_window import DashboardWindow


def scroll(name, count, location='inventory'):
    return {'DisplayName': f'제작 스크롤: {name}', 'Count': count, 'Location': location}


class ScrollInventoryTests(unittest.TestCase):
    """'보유 스크롤 모두 진행' 버튼 - user request 2026-09-20."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.window = DashboardWindow(Path(self._tmp.name), connect_on_start=False)

    def tearDown(self):
        self._tmp.cleanup()

    def test_known_scroll_is_queued_with_repeats_matching_its_count(self):
        self.window._on_scrolls_loaded([scroll('크레센트 엣지소드', 3)])
        [job] = self.window.queue.jobs
        self.assertEqual(job.spec.key, 'equipment_크레센트 엣지소드')
        self.assertEqual(job.repeats, 3)

    def test_repeats_are_capped_at_nine(self):
        self.window._on_scrolls_loaded([scroll('크레센트 엣지소드', 20)])
        [job] = self.window.queue.jobs
        self.assertEqual(job.repeats, 9)

    def test_unknown_scroll_is_silently_skipped(self):
        self.window._on_scrolls_loaded([scroll('아직 모르는 장비', 5)])
        self.assertEqual(self.window.queue.jobs, [])

    def test_non_inventory_location_is_ignored(self):
        # Domain fact: scrolls can't actually be stored outside inventory, but the
        # handler still shouldn't act on one if the CLI ever reported otherwise.
        self.window._on_scrolls_loaded([scroll('크레센트 엣지소드', 3, location='account_storage')])
        self.assertEqual(self.window.queue.jobs, [])

    def test_non_scroll_items_are_ignored(self):
        self.window._on_scrolls_loaded([{'DisplayName': '감자', 'Count': 50, 'Location': 'inventory'}])
        self.assertEqual(self.window.queue.jobs, [])

    def test_multiple_known_scrolls_are_all_queued(self):
        self.window._on_scrolls_loaded([
            scroll('크레센트 엣지소드', 1),
            scroll('그랜드 크로스보우', 2),
        ])
        keys = {job.spec.key: job.repeats for job in self.window.queue.jobs}
        self.assertEqual(keys, {'equipment_크레센트 엣지소드': 1, 'equipment_그랜드 크로스보우': 2})

    def test_zero_count_scroll_is_not_queued(self):
        self.window._on_scrolls_loaded([scroll('크레센트 엣지소드', 0)])
        self.assertEqual(self.window.queue.jobs, [])

    def test_extra_whitespace_in_the_scroll_name_still_matches_the_catalog_recipe(self):
        # The live API is known to be inconsistent about spacing within an item name
        # (recipe_info() already tolerates the same thing for get_craftable_items) -
        # _find_equipment_spec() normalizes so a scroll name with different spacing
        # than the catalog's own recipe name still resolves correctly.
        self.window._on_scrolls_loaded([scroll('로터스  힐링   완드', 3)])
        [job] = self.window.queue.jobs
        self.assertEqual(job.spec.key, 'equipment_로터스 힐링 완드')
        self.assertEqual(job.repeats, 3)


if __name__ == '__main__':
    unittest.main()
