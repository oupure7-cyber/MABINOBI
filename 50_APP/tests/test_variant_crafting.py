"""Same-name alternatives use supported commands and measured output only.

All ingredients/quantities here are synthetic, not real game recipe claims.
"""
import copy
import json
import unittest
from unittest.mock import patch

from app.dashboard.crafting_engine import CraftingWorker
from test_crafting_engine import Game


class VariantGame(Game):
    def __init__(self, variants, *, gather=(), owned=None, choose_last=False):
        super().__init__({name: specs[0] for name, specs in variants.items()}, gather=gather, owned=owned)
        self.variants = variants
        self.choose_last = choose_last
        self.gather_amount = 1
        self.calls = 0
        self.timeout_craft = False

    def variant_rows(self):
        rows = []
        for name, specs in self.variants.items():
            for spec in specs:
                row = self.rows({name: spec})['items'][0]
                if spec.get('locked'):
                    row.update(Craftable=False, Reason='insufficient_facility_level')
                rows.append(row)
        return rows

    def __call__(self, command, body=None, timeout=30):
        self.calls += 1
        if self.calls > 2500:
            raise AssertionError('Variant planner failed to make progress')
        if command == 'get_craftable_items':
            return {'items': self.variant_rows()}
        if command == 'execute_crafting':
            args = json.loads(body)
            assert set(args) == {'displayName', 'craftCount'}, 'No invented variant selector'
            name = args['displayName']
            ready = [spec for spec in self.variants[name] if not spec.get('locked') and
                     all(self.owned.get(n, 0) >= q for n, q in spec.get('ingredients', {}).items())]
            if not ready:
                return {'status': 'rejected', 'reason': 'not_enough_ingredient'}
            self.crafts[name] = ready[-1] if self.choose_last else ready[0]
            result = super().__call__(command, body, timeout)
            return {'error': 'timeout'} if self.timeout_craft else result
        return super().__call__(command, body, timeout)


class VariantCraftingTests(unittest.TestCase):
    def run_game(self, game, name='바람 마법 유탄', target=3, checkpoint=None):
        worker = CraftingWorker(name, target)
        if checkpoint is not None:
            worker.checkpoint = copy.deepcopy(checkpoint)
        errors = []
        worker.blocked.connect(errors.append)
        with patch('app.dashboard.crafting_engine.run_cli', game):
            worker.run()
        return worker, errors

    def test_nested_same_name_ingredient_uses_obtainable_alternative(self):
        game = VariantGame({
            '바람 마법 유탄': [{'produced': 3, 'ingredients': {'시험 유탄 부품': 2}}],
            '시험 유탄 부품': [
                {'ingredients': {'구할 수 없는 재료': 1}},
                {'ingredients': {'채집 광석': 2}},
            ],
        }, gather=('채집 광석',))
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(game.owned['바람 마법 유탄'], 3)
        self.assertEqual(worker.remaining, 0)
        self.assertEqual({a[1]['displayName'] for a in game.actions if a[0] == 'execute_gathering'}, {'채집 광석'})

    def test_ready_alternative_beats_locked_and_does_not_prepare_other_inputs(self):
        game = VariantGame({'바람 마법 유탄': [
            {'produced': 3, 'ingredients': {'귀한 꽃': 1}, 'locked': True},
            {'produced': 3, 'ingredients': {'광석': 1}},
        ]}, gather=('귀한 꽃',), owned={'광석': 1})
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(len(game.actions), 1)
        self.assertEqual(worker.checkpoint['completed'], 3)

    def test_smaller_obtainable_shortage_does_not_union_alternative_materials(self):
        game = VariantGame({'바람 마법 유탄': [
            {'produced': 3, 'ingredients': {'시험 꽃': 20}},
            {'produced': 3, 'ingredients': {'시험 광석': 2}},
        ]}, gather=('시험 꽃', '시험 광석'))
        worker, errors = self.run_game(game, target=6)
        self.assertEqual(errors, [])
        gathers = [a[1]['displayName'] for a in game.actions if a[0] == 'execute_gathering']
        self.assertEqual(gathers, ['시험 광석'] * 4)
        self.assertEqual(game.owned['바람 마법 유탄'], 6)
        self.assertNotIn('get_craftable_items:바람 마법 유탄', worker.checkpoint['observed'])

    def test_game_chooses_other_ready_yield_actual_count_controls_remaining(self):
        game = VariantGame({'바람 마법 유탄': [
            {'produced': 5, 'ingredients': {'철': 1}},
            {'produced': 10, 'ingredients': {'목재': 1}},
        ]}, owned={'철': 1, '목재': 1}, choose_last=True)
        worker, errors = self.run_game(game, target=15)
        self.assertEqual(errors, [])
        # Planner favors a 5-unit divisor of 15, while the game makes 10 first.
        # Only the 5-unit recipe remains ready after the larger one's input is used.
        self.assertEqual(worker.checkpoint['completed'], 15)
        self.assertEqual(game.owned['바람 마법 유탄'], 15)

    def test_uncertain_same_name_craft_cannot_be_retried_on_resume(self):
        game = VariantGame({'바람 마법 유탄': [
            {'produced': 3}, {'produced': 3, 'ingredients': {'꽃': 1}},
        ]}, owned={'꽃': 1})
        game.timeout_craft = True
        worker, errors = self.run_game(game)
        self.assertTrue(errors)
        self.assertIsNotNone(worker.checkpoint['pending'])
        actions = len(game.actions)
        _, errors = self.run_game(game, checkpoint=worker.checkpoint)
        self.assertTrue(errors)
        self.assertEqual(len(game.actions), actions)

    def test_insufficient_final_remainder_does_not_risk_known_larger_batch(self):
        game = VariantGame({'바람 마법 유탄': [{'produced': 3}, {'produced': 5}]})
        worker, errors = self.run_game(game, target=3)
        self.assertIn('목표', errors[0])
        self.assertEqual(game.actions, [])
        self.assertEqual(worker.remaining, 3)

    def test_pause_after_confirmed_variant_craft_records_actual_completion(self):
        game = VariantGame({'바람 마법 유탄': [
            {'produced': 3}, {'produced': 3, 'ingredients': {'꽃': 1}},
        ]}, owned={'꽃': 1})
        worker = CraftingWorker('바람 마법 유탄', 6)
        errors = []
        worker.blocked.connect(errors.append)
        def cli(command, body=None, timeout=30):
            result = game(command, body, timeout)
            if command == 'execute_crafting':
                worker.request_stop()
            return result
        with patch('app.dashboard.crafting_engine.run_cli', cli):
            worker.run()
        self.assertEqual(errors, [])
        self.assertEqual(worker.remaining, 3)
        self.assertEqual(worker.checkpoint['completed'], 3)
        self.assertIsNone(worker.checkpoint['pending'])

    def test_inventory_delta_outside_known_yields_is_not_credited(self):
        game = VariantGame({'바람 마법 유탄': [{'produced': 3}, {'produced': 5}]})
        def cli(command, body=None, timeout=30):
            result = game(command, body, timeout)
            if command == 'execute_crafting':
                game.owned['바람 마법 유탄'] += 100
            return result
        worker = CraftingWorker('바람 마법 유탄', 15)
        errors = []
        worker.blocked.connect(errors.append)
        with patch('app.dashboard.crafting_engine.run_cli', cli):
            worker.run()
        self.assertIn('실제 생산량', errors[0])
        self.assertEqual(worker.checkpoint['completed'], 0)
        self.assertIsNotNone(worker.checkpoint['pending'])


if __name__ == '__main__':
    unittest.main()
