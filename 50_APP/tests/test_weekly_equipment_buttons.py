"""Run: python -m unittest discover -s tests (no game CLI calls)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app.dashboard.equipment_crafting import TOWN_EQUIPMENT
from app.dashboard.modern_window import DashboardWindow


class WeeklyEquipmentButtonTests(unittest.TestCase):
    """'주간 제작(마을)'/'x5' 버튼 - 스크롤 주간 구매 한도 3개 반영, user request 2026-09-20."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.window = DashboardWindow(Path(self._tmp.name), connect_on_start=False)

    def tearDown(self):
        self._tmp.cleanup()

    def test_weekly_button_queues_the_towns_three_recipes_at_x6_each(self):
        self.window.add_weekly_equipment('던바튼', 1)
        jobs = self.window.queue.jobs
        self.assertEqual(len(jobs), 3)
        recipes = {job.spec.make_worker().recipe for job in jobs}
        self.assertEqual(recipes, set(TOWN_EQUIPMENT['던바튼']))
        for job in jobs:
            self.assertEqual(job.spec.make_worker().remaining, 6)

    def test_x5_button_queues_x10_and_x5_per_recipe_totaling_fifteen(self):
        self.window.add_weekly_equipment('콜헨', 5)
        jobs = self.window.queue.jobs
        self.assertEqual(len(jobs), 6)  # 3 recipes x (one x10 job + one x5 job)
        totals = {}
        for job in jobs:
            recipe = job.spec.make_worker().recipe
            totals[recipe] = totals.get(recipe, 0) + job.spec.make_worker().remaining
        self.assertEqual(set(totals), set(TOWN_EQUIPMENT['콜헨']))
        self.assertTrue(all(total == 15 for total in totals.values()))


if __name__ == '__main__':
    unittest.main()
