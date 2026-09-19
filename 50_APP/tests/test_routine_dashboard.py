"""Run: python -m unittest discover -s tests (no game CLI calls).

Covers RoutineDashboard's target-slider wiring (2026-09-20 redesign) - the sliders live in a
window that may outlive several worker instances (the "가공무한 1시간" JOB creates a fresh
AlteringRoutineWorker each run against the same long-lived embedded dashboard in
modern_window.py), so wire_targets() must push current values into a freshly-started worker
and keep re-targeting future drags there, without silently also nudging a worker from a
previous run.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app.dashboard.altering_routine import FAMILIES, AlteringRoutineWorker
from app.dashboard.routine_dashboard import RoutineDashboard


class RoutineDashboardTargetWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_one_control_per_family_defaulting_to_each_familys_default_idx(self):
        dashboard = RoutineDashboard()
        self.assertEqual(set(dashboard._controls), {f.key for f in FAMILIES})
        for f in FAMILIES:
            self.assertEqual(dashboard._controls[f.key].value(), f.default_target_idx)

    def test_wire_targets_pushes_current_slider_values_immediately(self):
        dashboard = RoutineDashboard()
        dashboard._controls['metal']._slider.setValue(4)
        worker = AlteringRoutineWorker()
        dashboard.wire_targets(worker)
        self.assertEqual(worker._target_for('metal'), 4)
        self.assertEqual(worker._target_for('wood'), next(f for f in FAMILIES if f.key == 'wood').default_target_idx)

    def test_dragging_after_wiring_updates_the_live_worker(self):
        dashboard = RoutineDashboard()
        worker = AlteringRoutineWorker()
        dashboard.wire_targets(worker)
        dashboard._controls['metal']._slider.setValue(6)
        self.assertEqual(worker._target_for('metal'), 6)

    def test_rewiring_a_new_worker_stops_retargeting_the_old_one(self):
        dashboard = RoutineDashboard()
        old_worker = AlteringRoutineWorker()
        dashboard.wire_targets(old_worker)
        dashboard._controls['metal']._slider.setValue(3)
        self.assertEqual(old_worker._target_for('metal'), 3)

        new_worker = AlteringRoutineWorker()
        dashboard.wire_targets(new_worker)
        dashboard._controls['metal']._slider.setValue(5)
        self.assertEqual(new_worker._target_for('metal'), 5)
        self.assertEqual(old_worker._target_for('metal'), 3)  # frozen at its last value


if __name__ == '__main__':
    unittest.main()
