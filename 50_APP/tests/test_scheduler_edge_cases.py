"""Additional scheduler regressions against the documented connector semantics.

All recipes are synthetic. Only production runs concurrently; character actions
remain serial. The fixture exposes shortages, not a complete recipe bill.
"""
import copy
import unittest
from unittest.mock import patch

from app.dashboard.crafting_engine import CraftingWorker
from test_crafting_scheduler import DelayedGame


class LaggedQueueGame(DelayedGame):
    stale_rows = None

    def __call__(self, command, body=None, timeout=30):
        if command == 'get_altering_works' and self.stale_rows is not None:
            rows, self.stale_rows = self.stale_rows, None
            return {'works': rows}
        before = copy.deepcopy(self.work_rows()) if command == 'execute_altering' else None
        result = super().__call__(command, body, timeout)
        if command == 'execute_altering':
            # The first queue read after confirmed registration still shows
            # the prior batch snapshot, without the newly accepted work.
            self.stale_rows = before
        return result


class SchedulerEdgeCaseTests(unittest.TestCase):
    def run_game(self, game, target=1, checkpoint=None, worker=None):
        worker = worker or CraftingWorker(game.final_name, target)
        if checkpoint is not None:
            worker.checkpoint = copy.deepcopy(checkpoint)
        errors = []
        worker.blocked.connect(errors.append)
        with patch('app.dashboard.crafting_engine.run_cli', game), \
             patch('app.dashboard.crafting_engine.time.monotonic', side_effect=lambda: game.now), \
             patch.object(worker, '_sleep', side_effect=game.sleep):
            worker.run()
        return worker, errors

    def registrations(self, game):
        return [a for a in game.actions if a['command'] == 'execute_altering']

    def test_completed_sibling_recipes_are_received_together_without_reproduction(self):
        game = DelayedGame({'재료 A': 6, '재료 B': 4, '채집재': 1}, {
            '재료 A': {'facility': '공유 생산소', 'produced': 2},
            '재료 B': {'facility': '공유 생산소', 'produced': 2}}, gather=('채집재',))
        game.add_existing('재료 A', 3)
        game.add_existing('재료 B', 2)
        game.now += 1000  # Both recipe kinds have finished at the shared facility.
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(self.registrations(game), [])
        collections = [a for a in game.actions if a['command'] == 'complete_altering_work']
        self.assertEqual(len(collections), 1)
        self.assertEqual(game.works, [])
        self.assertEqual(game.owned['재료 A'], 0)
        self.assertEqual(game.owned['재료 B'], 0)
        self.assertEqual(worker.remaining, 0)

    def test_two_independent_facilities_fill_before_first_idle_poll(self):
        game = DelayedGame({'재료 A': 6, '재료 B': 8}, {
            '재료 A': {'facility': '생산소 A', 'produced': 2, 'duration': 120},
            '재료 B': {'facility': '생산소 B', 'produced': 2, 'duration': 120}})
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertTrue(game.sleeps)
        first_wait = game.sleeps[0]['works']
        self.assertEqual(sum(w['recipe'] == '재료 A' for w in first_wait), 3)
        self.assertEqual(sum(w['recipe'] == '재료 B' for w in first_wait), 4)
        self.assertEqual(len(self.registrations(game)), 7)
        self.assertEqual(worker.remaining, 0)

    def test_round_up_only_the_net_shortfall_after_owned_and_queued_supply(self):
        game = DelayedGame({'재료': 12}, {'재료': {'facility': '생산소', 'produced': 5}},
                           owned={'재료': 1})
        game.add_existing('재료')
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        # 12 needed - 1 owned - 5 pending = 6 short, requiring two batches.
        self.assertEqual(len(self.registrations(game)), 2)
        self.assertEqual(game.owned['재료'], 4)
        self.assertEqual(worker.remaining, 0)

    def test_resume_reconciles_user_collection_during_pause(self):
        game = DelayedGame({'재료': 6, '채집재': 1}, {
            '재료': {'facility': '생산소', 'produced': 2}}, gather=('채집재',))
        worker = CraftingWorker(game.final_name, 1)
        game.after_registration = lambda: worker.request_stop() if len(self.registrations(game)) == 2 else None
        worker, errors = self.run_game(game, worker=worker)
        self.assertEqual(errors, [])
        self.assertEqual(len(game.works), 2)
        game.after_registration = None
        game.now += 1000
        # The user can collect facility output while this program is paused.
        game('complete_altering_work', '{"displayName": "재료"}')
        resumed, errors = self.run_game(game, checkpoint=worker.checkpoint)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.registrations(game)), 3)
        self.assertEqual(game.owned['재료'], 0)
        self.assertTrue(all(s['owned'].get('채집재', 0) >= 1 for s in game.sleeps))
        self.assertEqual(resumed.remaining, 0)

    def test_hidden_initially_sufficient_ingredient_is_discovered_after_consumption(self):
        game = DelayedGame({'재료 A': 2, '재료 B': 1}, {
            '재료 A': {'facility': '생산소 A', 'produced': 2},
            '재료 B': {'facility': '생산소 B', 'produced': 1}}, owned={'재료 B': 1})
        worker, errors = self.run_game(game, target=3)
        self.assertEqual(errors, [])
        # B is absent from MissingIngredients until its initial stock is used.
        # Discover that shortage then; never claim a full bill was available.
        registrations = self.registrations(game)
        self.assertEqual(sum(a['name'] == '재료 A' for a in registrations), 3)
        self.assertEqual(sum(a['name'] == '재료 B' for a in registrations), 2)
        self.assertEqual(game.owned[game.final_name], 3)
        self.assertEqual(worker.remaining, 0)

    def test_old_visible_work_does_not_erase_confirmation_of_new_unobserved_work(self):
        game = LaggedQueueGame({'재료': 2}, {'재료': {'facility': '생산소', 'produced': 1}})
        game.add_existing('재료')
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.registrations(game)), 1)
        self.assertEqual(worker.remaining, 0)

    def test_unobserved_sibling_registration_also_reserves_its_facility_slot(self):
        game = LaggedQueueGame({'재료 A': 6, '재료 B': 2}, {
            '재료 A': {'facility': '공유 생산소', 'produced': 1},
            '재료 B': {'facility': '공유 생산소', 'produced': 1}})
        game.add_existing('재료 A', 5)
        game.add_existing('재료 B')
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.registrations(game)), 2)
        self.assertTrue(all(a['occupancy_after'] <= 7 for a in self.registrations(game)))
        self.assertEqual(worker.remaining, 0)


if __name__ == '__main__':
    unittest.main()
