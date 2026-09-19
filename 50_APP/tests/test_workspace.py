"""Run: python -m unittest discover -s tests (no game CLI calls)."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from app.dashboard.modern_window import WorkQueue, JobSpec


class FakeWorker(QObject):
    status = Signal(str)
    blocked = Signal(str)
    finished = Signal()
    def start(self): pass
    def request_stop(self): self.stop_requested = True


class QueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.queue = WorkQueue()
        self.workers = []
        def factory():
            worker = FakeWorker()
            self.workers.append(worker)
            return worker
        self.spec = JobSpec('gather_test', '테스트', factory)
        self.factory = factory

    def tearDown(self):
        self.queue.deleteLater()

    def test_explicit_start_and_pause_at_request_boundary(self):
        q = self.queue
        q.add(self.spec); q.add(self.spec)
        self.assertIsNone(q.worker)
        q.toggle_pause()
        first = q.worker
        q.toggle_pause()
        self.assertIs(q.worker, first)
        first.finished.emit()
        self.assertIsNone(q.worker)
        self.assertEqual(len(q.jobs), 1)
        self.assertTrue(q.paused)

    def test_block_preserves_job_until_user_resumes(self):
        q = self.queue; q.add(self.spec); q.toggle_pause()
        q.worker.blocked.emit('confirmation')
        q.worker.finished.emit()
        self.assertTrue(q.blocked)
        self.assertEqual(q.jobs[0].repeats, 1)
        q.toggle_pause()
        self.assertFalse(q.blocked)
        q.worker.finished.emit()
        self.assertEqual(q.jobs, [])

    def test_skip_waits_for_finished_before_next_worker(self):
        q = self.queue; q.add(self.spec); q.add(self.spec); q.toggle_pause()
        first = q.worker; q.skip_current()
        self.assertIs(q.worker, first)
        first.finished.emit()
        self.assertEqual(len(self.workers), 2)
        self.assertIs(q.worker, self.workers[1])
        q.worker.finished.emit()

    def test_infinite_pause_preserves_queue_entry(self):
        q = self.queue
        q.add(JobSpec('altering_infinite', '무한가공소', self.factory))
        q.toggle_pause(); worker = q.worker; q.toggle_pause()
        self.assertTrue(worker.stop_requested)
        worker.finished.emit()
        self.assertEqual(len(q.jobs), 1)
        self.assertEqual(q.jobs[0].repeats, 1)

    def test_music_guard_prevents_start(self):
        q = self.queue; q.add(self.spec)
        q.activity_guard = lambda: True
        q.toggle_pause()
        self.assertIsNone(q.worker)
        self.assertTrue(q.paused)

    def test_active_job_cannot_be_deleted_or_reordered(self):
        q = self.queue; q.add(self.spec); q.add(self.spec); q.toggle_pause()
        current = q.jobs[0]
        q.remove(current); q.move_job(current, 1)
        self.assertIs(q.jobs[0], current)
        self.assertEqual(len(q.jobs), 2)
        q.toggle_pause(); q.worker.finished.emit()


if __name__ == '__main__': unittest.main()
