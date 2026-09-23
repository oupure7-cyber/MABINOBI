"""Current-character ownership freshness without any game CLI calls."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app import character_profiles
from app.dashboard.character_watcher import CharacterIdentifyWorker, CharacterWatcher, PollWorker


MODULE = "app.dashboard.character_watcher"


def money(n=1):
    return [{"DisplayName": "냥 토큰", "Amount": n}, {"DisplayName": "하트 토큰", "Amount": n}]


def info():
    return {"EnabledCombatJobDisplayName": "수도사", "RealmName": "칼릭스", "CombatScore": {"Value": 88221}}


def items(n=5):
    return [{"Location": "inventory", "DisplayName": "나뭇가지", "Count": n}]


class OwnedWatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.watcher = CharacterWatcher(self.root)
        self.watcher._timer.stop()
        self.events = []
        self.watcher.inventory_updated.connect(self.events.append)
        self.profile = character_profiles.match_or_create(self.root, info(), money(), items())
        self.watcher._active_profile = self.profile
        self.watcher._last_currencies = money()

    def tearDown(self):
        self.watcher._identify_worker = None
        self.watcher._poll_worker = None
        self.watcher.stop()
        self.temp.cleanup()

    def test_unchanged_valid_poll_emits_fresh_profile_without_disk_rewrite(self):
        self.watcher._active_profile["last_seen"] = "old timestamp"
        with patch(f"{MODULE}.character_profiles.refresh_items") as refresh:
            self.watcher._on_polled(money(), items())
        refresh.assert_not_called()
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["inventory"], items())
        self.assertNotEqual(self.events[0]["last_seen"], "old timestamp")

    def test_changed_poll_updates_profile_and_emits_new_count(self):
        updates = []
        self.watcher.profile_updated.connect(lambda profile, all_profiles: updates.append(profile))
        self.watcher._on_polled(money(), items(9))
        self.assertEqual(self.events[-1]["inventory"][0]["Count"], 9)
        self.assertEqual(updates[-1]["inventory"][0]["Count"], 9)
        self.assertEqual(character_profiles.load_profiles(self.root)[0]["inventory"][0]["Count"], 9)

    def test_missing_currency_response_keeps_old_snapshot_without_trusting_items(self):
        self.watcher._on_polled(None, items(999))
        self.assertEqual(self.events, [])
        self.assertEqual(self.watcher._active_profile["inventory"], items())

    def test_failed_items_poll_is_unknown_and_does_not_zero_saved_inventory(self):
        for value in ({"error": "offline"}, [None], [{"DisplayName": "broken"}]):
            with self.subTest(value=value):
                self.watcher._on_polled(money(), value)
                self.assertIsNone(self.events[-1])
                self.assertEqual(self.watcher._active_profile["inventory"], items())

    def test_skipped_items_poll_keeps_snapshot_without_refreshing_freshness(self):
        self.watcher._active_profile["last_seen"] = "last successful poll"
        self.watcher._on_polled(money(), None)
        self.assertEqual(self.events, [])
        self.assertEqual(self.watcher._active_profile["last_seen"], "last successful poll")
        self.assertEqual(self.watcher._active_profile["inventory"], items())

    def test_explicit_currency_error_invalidates_without_trusting_item_response(self):
        self.watcher._on_polled({"error": "offline"}, items(999))
        self.assertEqual(self.events, [None])
        self.assertEqual(self.watcher._active_profile["inventory"], items())

    def test_explicit_item_error_still_invalidates_if_currency_poll_was_skipped(self):
        self.watcher._on_polled(None, {"error": "offline"})
        self.assertEqual(self.events, [None])
        self.assertEqual(self.watcher._active_profile["inventory"], items())

    def test_empty_successful_items_poll_means_confirmed_zero(self):
        self.watcher._on_polled(money(), [])
        self.assertEqual(self.events[-1]["inventory"], [])

    def test_switch_invalidates_immediately_and_never_writes_new_items_to_old_profile(self):
        with patch(f"{MODULE}.CharacterIdentifyWorker") as worker, patch(f"{MODULE}.character_profiles.refresh_items") as refresh:
            self.watcher._on_polled(money(2), items(999))
            worker.return_value.start.assert_called_once()
            refresh.assert_not_called()
        self.assertEqual(self.events, [None])
        self.assertIsNone(self.watcher._active_profile)
        self.assertTrue(self.watcher._identifying)
        self.assertEqual(character_profiles.load_profiles(self.root)[0]["inventory"], items())

    def test_identification_blocks_timer_poll_and_any_late_poll_results(self):
        self.watcher._identifying = True
        with patch(f"{MODULE}.PollWorker") as poll, patch(f"{MODULE}.character_profiles.refresh_items") as refresh:
            self.watcher._tick()
            self.watcher._on_polled(money(), items(999))
            poll.assert_not_called()
            refresh.assert_not_called()
        self.assertEqual(self.events, [])

    def test_running_identify_thread_also_blocks_new_poll(self):
        self.watcher._identify_worker = MagicMock()
        self.watcher._identify_worker.isRunning.return_value = True
        with patch(f"{MODULE}.PollWorker") as poll:
            self.watcher._tick()
            poll.assert_not_called()

    def test_finished_poll_waits_for_queued_result_before_another_poll_starts(self):
        self.watcher._poll_pending = True
        self.watcher._poll_worker = MagicMock()
        self.watcher._poll_worker.isRunning.return_value = False
        with patch(f"{MODULE}.PollWorker") as poll:
            self.watcher._tick()
            poll.assert_not_called()
        self.watcher._on_polled(money(), items())
        self.assertFalse(self.watcher._poll_pending)

    def test_failed_identification_does_not_create_empty_profile_and_retries(self):
        self.watcher._identifying = True
        self.watcher._on_identified(info(), None)
        self.assertEqual(self.events, [None])
        self.assertIsNone(self.watcher._active_profile)
        self.assertFalse(self.watcher._identifying)
        self.assertEqual(character_profiles.load_profiles(self.root)[0]["inventory"], items())
        with patch(f"{MODULE}.CharacterIdentifyWorker") as worker:
            self.watcher._on_polled(money(), items())
            worker.return_value.start.assert_called_once()

    def test_error_or_incomplete_character_info_is_not_a_real_identity(self):
        invalid = ({}, {"error": "offline"}, {**info(), "EnabledCombatJobDisplayName": ""},
                   {**info(), "RealmName": ""}, {**info(), "CombatScore": {}},
                   {**info(), "CombatScore": {"Value": True}},
                   {**info(), "CombatScore": {"Value": float("nan")}})
        with patch(f"{MODULE}.character_profiles.match_or_create") as save:
            for value in invalid:
                with self.subTest(value=value):
                    self.watcher._on_identified(value, items())
                    self.assertIsNone(self.events[-1])
                    self.assertIsNone(self.watcher._active_profile)
            save.assert_not_called()

    def test_successful_identification_emits_current_snapshot(self):
        self.watcher._identifying = True
        self.watcher._on_identified(info(), items(12))
        self.assertEqual(self.events[-1]["inventory"], items(12))
        self.assertFalse(self.watcher._identifying)

    def test_identify_worker_preserves_failed_item_response_as_none(self):
        worker = CharacterIdentifyWorker()
        received = []
        worker.identified.connect(lambda my_info, item_list: received.append((my_info, item_list)))
        with patch(f"{MODULE}.run_cli", side_effect=[info(), {"error": "offline"}]) as cli:
            worker.run()
        self.assertEqual(received, [(info(), None)])
        self.assertEqual([call.args for call in cli.call_args_list], [("get_my_info",), ("get_items",)])

    def test_identify_worker_reports_io_failure_so_retry_is_not_stuck(self):
        worker = CharacterIdentifyWorker()
        received = []
        worker.identified.connect(lambda my_info, item_list: received.append((my_info, item_list)))
        with patch(f"{MODULE}.run_cli", side_effect=PermissionError("unavailable")):
            worker.run()
        self.assertEqual(received, [(None, None)])

    def test_poll_worker_preserves_skipped_and_explicit_error_results(self):
        for currencies, item_list in ((money(), None), (None, items()),
                                       (money(), {"error": "offline"}),
                                       ({"error": "offline"}, items()), (money(), [])):
            with self.subTest(currencies=currencies, item_list=item_list):
                worker = PollWorker()
                received = []
                worker.polled.connect(lambda cur, inv: received.append((cur, inv)))
                with patch(f"{MODULE}.try_run_cli", side_effect=[currencies, item_list]) as cli:
                    worker.run()
                self.assertEqual(received, [(currencies, item_list)])
                self.assertEqual([call.args for call in cli.call_args_list], [("get_currencies",), ("get_items",)])

    def test_poll_worker_io_failure_is_not_reported_as_busy(self):
        worker = PollWorker()
        received = []
        worker.polled.connect(lambda cur, inv: received.append((cur, inv)))
        with patch(f"{MODULE}.try_run_cli", side_effect=PermissionError("unavailable")):
            worker.run()
        self.assertEqual(received, [({"error": "poll_failed"}, {"error": "poll_failed"})])


if __name__ == "__main__":
    unittest.main()
