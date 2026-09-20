"""Snapshot display checks without game or network calls."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app.dashboard.altering_routine import ALL_MATERIAL_NAMES
from app.dashboard.routine_dashboard import RoutineDashboard, FacilitySlots, _ordered_material_names


class RoutineLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.dashboard = RoutineDashboard()

    def tearDown(self):
        self.dashboard.deleteLater()

    def test_snapshot_updates_both_material_columns_without_losing_names(self):
        names = _ordered_material_names()
        self.assertEqual(set(names), set(ALL_MATERIAL_NAMES))
        values = {name: 2000 + i for i, name in enumerate(names)}
        self.dashboard._on_snapshot({'materials': values})
        self.assertEqual(self.dashboard._table.rowCount(), (len(names) + 1) // 2)
        self.assertEqual(set(self.dashboard._material_column.values()), {1, 3})
        for name, value in values.items():
            row = self.dashboard._material_row[name]
            column = self.dashboard._material_column[name]
            self.assertEqual(self.dashboard._table.item(row, column - 1).text(), name)
            self.assertEqual(self.dashboard._table.item(row, column).text(), f'{value:,}')

    def test_unknown_is_not_displayed_as_empty_until_first_snapshot(self):
        slots = self.dashboard._queue_slots['metal']
        self.assertEqual(slots.states, ['unknown'] * 7)
        self.dashboard._on_snapshot({'queue': {'metal': 0}})
        self.assertEqual(slots.states, ['empty'] * 7)
        self.assertEqual(self.dashboard._queue_label['metal'].text(), '등록된 작업 없음')

    def test_completed_and_unfinished_occupancy_are_separate(self):
        self.dashboard._on_snapshot({'queue': {'metal': 5}, 'queue_completed': {'metal': 2}})
        self.assertEqual(self.dashboard._queue_slots['metal'].states,
                         ['completed'] * 2 + ['occupied'] * 3 + ['empty'] * 2)
        self.assertEqual(self.dashboard._queue_count['metal'].text(), '5 / 7')
        slots = FacilitySlots()
        slots.update_counts(20, 30)
        self.assertEqual(slots.states, ['completed'] * 7)
        slots.deleteLater()

    def test_blocked_hides_stale_counts_and_ignores_later_snapshots(self):
        forwarded = []
        self.dashboard.snapshot_received.connect(forwarded.append)
        self.dashboard._on_snapshot({'queue': {'metal': 3}})
        self.dashboard._on_blocked('confirmation required')
        self.dashboard._on_snapshot({'queue': {'metal': 0}})
        self.assertTrue(self.dashboard._blocked)
        self.assertTrue(self.dashboard._content.isHidden())
        self.assertFalse(self.dashboard._alert.isHidden())
        self.assertEqual(self.dashboard._queue_count['metal'].text(), '3 / 7')
        self.assertEqual(len(forwarded), 1)


if __name__ == '__main__':
    unittest.main()
