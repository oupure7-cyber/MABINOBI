"""Environment HUD integration without a real game or connector invocation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import threading
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRectF, QThread, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.dashboard.overlay import EnvironmentOverlay, EnvironmentOverlayController


class GameWindow:
    def __init__(self, visible=True):
        self.rect = QRectF(50, 100, 1200, 800) if visible else None

    def rectangle(self):
        return self.rect


class EnvironmentHudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_compact_hud_is_parentless_borderless_regular_and_eighty_percent(self):
        panel = EnvironmentOverlay(compact=True)
        try:
            panel.set_data({'GameSpaceDisplayName':'던바튼', 'Weather':'맑음', 'ErinnNow':'12:00'})
            self.assertIsNone(panel.parentWidget())
            self.assertEqual((panel.width(), panel.height()), (240,35))
            self.assertFalse(panel._label.font().bold())
            self.assertNotIn('<b>', panel._label.text())
            self.assertIn('던바튼', panel._label.text())
            self.assertEqual(panel.grab().toImage().pixelColor(0,0).alpha(), 0)
        finally:
            panel.close()

    def test_failed_environment_read_preserves_the_last_known_values(self):
        panel = EnvironmentOverlay(compact=True)
        try:
            panel.set_data({'GameSpaceDisplayName':'던바튼', 'Weather':'비', 'ErinnNow':'18:00'})
            previous = panel._label.text()
            for data in (None, {'pipe':'disconnected'}, {'error':'timeout'}, {}):
                panel.set_data(data)
                self.assertEqual(panel._label.text(), previous)
        finally:
            panel.close()

    def test_selftest_mode_never_polls_even_if_enabled_above_a_visible_game(self):
        controller = EnvironmentOverlayController(GameWindow(), polling_allowed=False)
        try:
            with patch('app.dashboard.overlay.EnvironmentPollWorker') as factory:
                controller.set_enabled(True)
                controller._poll()
                QTest.qWait(5)
                factory.assert_not_called()
            self.assertFalse(controller._poll_timer.isActive())
        finally:
            controller.close()

    def test_no_foreground_game_means_no_query_and_no_display(self):
        controller = EnvironmentOverlayController(GameWindow(visible=False))
        try:
            with patch('app.dashboard.overlay.EnvironmentPollWorker') as factory:
                controller.set_enabled(True)
                controller._poll()
                factory.assert_not_called()
            self.assertFalse(controller.panel.isVisible())
        finally:
            controller.close()

    def test_slow_read_runs_outside_gui_and_cannot_spawn_overlapping_queries(self):
        controller = EnvironmentOverlayController(GameWindow())
        entered, release = threading.Event(), threading.Event()
        threads = []
        gui_events = []
        def slow_read(*args, **kwargs):
            threads.append(QThread.currentThread())
            entered.set()
            release.wait(2)
            return {'GameSpaceDisplayName':'시험 지역', 'Weather':'눈', 'ErinnNow':'06:00'}
        try:
            with patch('app.dashboard.overlay.try_run_cli', side_effect=slow_read) as cli:
                controller.set_enabled(True)
                self.assertTrue(entered.wait(.5))
                first_worker = controller.worker
                controller._poll()
                self.assertIs(controller.worker, first_worker)
                QTimer.singleShot(0, lambda: gui_events.append(True))
                QTest.qWait(10)
                self.assertTrue(gui_events)
                self.assertNotEqual(threads[0], self.app.thread())
                self.assertEqual(cli.call_count, 1)
                release.set()
                self.assertTrue(first_worker.wait(1000))
                self.app.processEvents()
                self.assertIn('시험 지역', controller.panel._label.text())
        finally:
            release.set()
            if controller.worker is not None:
                controller.worker.wait(1000)
                self.app.processEvents()
            controller.close()

    def test_disabling_stops_timers_and_late_result_cannot_reopen_panel(self):
        controller = EnvironmentOverlayController(GameWindow(), polling_allowed=False)
        try:
            controller.set_enabled(True)
            controller.set_enabled(False)
            controller._on_result({'GameSpaceDisplayName':'늦은 응답'})
            controller._position()
            self.assertFalse(controller._position_timer.isActive())
            self.assertFalse(controller._poll_timer.isActive())
            self.assertFalse(controller.panel.isVisible())
            self.assertEqual(controller.panel._label.text(), '-')
        finally:
            controller.close()


if __name__ == '__main__':
    unittest.main()
