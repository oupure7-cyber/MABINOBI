"""Behavioral scheduler checks with delayed, shared, finite production facilities.

Recipes and facilities here are synthetic. No real connector is invoked.
"""
import copy
import json
import unittest
from unittest.mock import patch

from app.dashboard.crafting_engine import CraftingWorker


class DelayedGame:
    def __init__(self, ingredients, altering, *, owned=None, gather=()):
        self.final_name = '시험 완성품'
        self.final_ingredients = ingredients
        self.altering = altering
        self.owned = dict(owned or {})
        self.gatherable = set(gather)
        self.now = 1000.0
        self.works = []
        self.actions = []
        self.sleeps = []
        self.query_count = 0
        self.after_registration = None
        self.timeout_registration = False

    def shortages(self, ingredients):
        return [{'DisplayName': name, 'Required': count, 'Owned': self.owned.get(name, 0)}
                for name, count in ingredients.items() if self.owned.get(name, 0) < count]

    def recipe(self, name, ingredients, produced, altering=False):
        missing = self.shortages(ingredients)
        return {'DisplayName': name, 'MissingIngredients': missing,
                'ProducedPerWork' if altering else 'ProducedPerCraft': produced,
                'Alterable' if altering else 'Craftable': not missing,
                'Reason': 'not_enough_ingredient' if missing else None}

    def add_existing(self, name, count=1):
        spec = self.altering[name]
        for _ in range(count):
            start = max([self.now] + [w['end'] for w in self.works if w['facility'] == spec['facility']])
            self.works.append({'recipe': name, 'facility': spec['facility'], 'start': start,
                               'end': start + spec.get('duration', 30), 'produced': spec['produced']})

    def work_rows(self):
        return [{'DisplayName': w['recipe'], 'FacilityName': w['facility'],
                 'State': 'Completed' if w['end'] <= self.now else 'InProgress' if w['start'] <= self.now else 'NotStarted',
                 'IsCompleted': w['end'] <= self.now,
                 'RemainingSeconds': max(0, w['end'] - self.now) if w['start'] <= self.now else 0}
                for w in self.works]

    def sleep(self, seconds):
        self.sleeps.append({'time': self.now, 'owned': dict(self.owned), 'works': copy.deepcopy(self.works)})
        self.now += max(seconds, 1)

    def consume(self, ingredients):
        for name, count in ingredients.items():
            if self.owned.get(name, 0) < count:
                raise AssertionError('Attempted production without sufficient ingredients: ' + name)
        for name, count in ingredients.items(): self.owned[name] -= count

    def __call__(self, command, body=None, timeout=30):
        self.query_count += 1
        if self.query_count > 20000: raise AssertionError('Scheduler did not converge')
        args = json.loads(body) if body else {}
        if command == 'get_craftable_items':
            return {'items': [self.recipe(self.final_name, self.final_ingredients, 1)]}
        if command == 'get_alterable_items':
            return {'items': [self.recipe(n, s.get('ingredients', {}), s['produced'], True)
                              for n, s in self.altering.items()]}
        if command == 'get_gatherable_items':
            return {'items': [{'DisplayName': n, 'ToolOk': True} for n in sorted(self.gatherable)]}
        if command == 'get_items':
            return [{'DisplayName': args['name'], 'Count': self.owned.get(args['name'], 0)}]
        if command == 'get_altering_works': return {'works': self.work_rows()}
        record = {'command': command, 'name': args.get('displayName'), 'time': self.now,
                  'owned_before': dict(self.owned), 'works_before': copy.deepcopy(self.works)}
        self.actions.append(record)
        self.now += .1
        name = args.get('displayName')
        if command == 'execute_gathering':
            if name not in self.gatherable: raise AssertionError('Unknown gathering action')
            self.owned[name] = self.owned.get(name, 0) + 100
            return {'status': 'accepted', 'result': 'completed', 'gained': 100}
        if command == 'execute_altering':
            spec = self.altering[name]
            occupied = sum(w['facility'] == spec['facility'] for w in self.works)
            if occupied >= 7: raise AssertionError('Exceeded shared facility capacity')
            self.consume(spec.get('ingredients', {}))
            self.add_existing(name)
            record['occupancy_after'] = occupied + 1
            if self.after_registration: self.after_registration()
            if self.timeout_registration:
                return {'error': 'timeout'}
            return {'status': 'accepted', 'result': 'started'}
        if command == 'complete_altering_work':
            matching = [w for w in self.works if w['recipe'] == name and w['end'] <= self.now]
            if not matching: raise AssertionError('Tried collecting unfinished work')
            facility = matching[0]['facility']
            completed = [w for w in self.works if w['facility'] == facility and w['end'] <= self.now]
            for w in completed:
                product = self.altering[w['recipe']].get('output', w['recipe'])
                self.owned[product] = self.owned.get(product, 0) + w['produced']
                self.works.remove(w)
            return {'status': 'accepted', 'collected': len(completed)}
        if command == 'execute_crafting':
            if name != self.final_name or args.get('craftCount') != 1: raise AssertionError('Unexpected final craft')
            self.consume(self.final_ingredients)
            self.owned[name] = self.owned.get(name, 0) + 1
            return {'status': 'accepted', 'result': 'completed', 'craftCount': 1}
        raise AssertionError(command)


class ProductionSchedulingTests(unittest.TestCase):
    def run_game(self, game, target=1, checkpoint=None, worker=None):
        worker = worker or CraftingWorker(game.final_name, target)
        if checkpoint is not None: worker.checkpoint = copy.deepcopy(checkpoint)
        errors = []
        worker.blocked.connect(errors.append)
        with patch('app.dashboard.crafting_engine.run_cli', game), \
             patch('app.dashboard.crafting_engine.time.monotonic', side_effect=lambda: game.now), \
             patch.object(worker, '_sleep', side_effect=game.sleep):
            worker.run()
        return worker, errors

    def registrations(self, game, name=None):
        return [a for a in game.actions if a['command'] == 'execute_altering' and (name is None or a['name'] == name)]

    def test_fill_seven_then_gather_independent_material_before_waiting(self):
        game = DelayedGame({'가공재 A': 14, '채집재 B': 3}, {
            '가공재 A': {'facility': '시험 시설 A', 'produced': 2, 'ingredients': {'원료 A': 1}}},
            owned={'원료 A': 7}, gather=('채집재 B',))
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        first_gather = next(a for a in game.actions if a['command'] == 'execute_gathering')
        self.assertEqual(len(first_gather['works_before']), 7)
        self.assertTrue(all(w['end'] > first_gather['time'] for w in first_gather['works_before']))
        self.assertTrue(all(s['owned'].get('채집재 B', 0) >= 3 for s in game.sleeps))
        self.assertEqual(len(self.registrations(game)), 7)
        self.assertEqual(worker.remaining, 0)

    def test_only_needed_batches_including_inventory_and_existing_work(self):
        game = DelayedGame({'가공재': 5}, {'가공재': {'facility': '시험 시설', 'produced': 2}}, owned={'가공재': 1})
        game.add_existing('가공재')
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.registrations(game)), 1)
        self.assertEqual(game.owned['가공재'], 0)
        self.assertEqual(worker.remaining, 0)

    def test_existing_work_covering_demand_does_not_stop_other_gathering(self):
        game = DelayedGame({'가공재': 5, '원료': 1}, {'가공재': {'facility': '시험 시설', 'produced': 2}},
                           owned={'가공재': 1}, gather=('원료',))
        game.add_existing('가공재', 2)
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(self.registrations(game), [])
        self.assertEqual(game.actions[0]['command'], 'execute_gathering')
        self.assertTrue(all(s['owned'].get('원료', 0) >= 1 for s in game.sleeps))
        self.assertEqual(worker.remaining, 0)

    def test_shared_facility_counts_other_recipes_toward_capacity(self):
        game = DelayedGame({'가공재 A': 12, '원료': 1}, {
            '가공재 A': {'facility': '공유 시설', 'produced': 2},
            '다른 생산물': {'facility': '공유 시설', 'produced': 1}}, gather=('원료',))
        game.add_existing('다른 생산물', 5)
        game.add_existing('가공재 A')
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        first_gather = next(a for a in game.actions if a['command'] == 'execute_gathering')
        self.assertEqual(len(first_gather['works_before']), 7)
        self.assertTrue(all(a['occupancy_after'] <= 7 for a in self.registrations(game)))
        self.assertEqual(len(self.registrations(game, '가공재 A')), 5)
        self.assertEqual(worker.remaining, 0)

    def test_unknown_new_facility_can_start_while_unrelated_facility_is_busy(self):
        game = DelayedGame({'가공재 A': 2}, {
            '가공재 A': {'facility': '새 시설', 'produced': 1},
            '다른 생산물': {'facility': '기존 시설', 'produced': 1}})
        game.add_existing('다른 생산물', 7)
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.registrations(game)), 2)
        self.assertEqual(worker.remaining, 0)

    def test_recursive_batch_demand_and_independent_gathering(self):
        game = DelayedGame({'최종 재료 A': 6, '채집재 B': 1}, {
            '최종 재료 A': {'facility': '상위 시설', 'produced': 2, 'ingredients': {'중간재 C': 3}},
            '중간재 C': {'facility': '하위 시설', 'produced': 3, 'ingredients': {'원광': 4}}},
            gather=('원광', '채집재 B'))
        worker, errors = self.run_game(game)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.registrations(game, '최종 재료 A')), 3)
        self.assertEqual(len(self.registrations(game, '중간재 C')), 3)
        self.assertTrue(all(s['owned'].get('채집재 B', 0) >= 1 for s in game.sleeps))
        self.assertEqual(worker.remaining, 0)

    def test_resume_reuses_multiple_registered_batches(self):
        game = DelayedGame({'가공재': 10, '원료': 1}, {'가공재': {'facility': '시험 시설', 'produced': 1}}, gather=('원료',))
        worker = CraftingWorker(game.final_name, 1)
        game.after_registration = lambda: worker.request_stop() if len(self.registrations(game)) == 3 else None
        worker, errors = self.run_game(game, worker=worker)
        self.assertEqual(errors, [])
        self.assertEqual(len(game.works), 3)
        self.assertEqual(worker.remaining, 1)
        game.after_registration = None
        resumed, errors = self.run_game(game, checkpoint=worker.checkpoint)
        self.assertEqual(errors, [])
        self.assertEqual(len(self.registrations(game)), 10)
        self.assertTrue(all(a['occupancy_after'] <= 7 for a in self.registrations(game)))
        self.assertEqual(resumed.remaining, 0)

    def test_uncertain_registration_never_duplicates_on_resume(self):
        game = DelayedGame({'가공재': 5}, {'가공재': {'facility': '시험 시설', 'produced': 1}})
        game.timeout_registration = True
        worker, errors = self.run_game(game)
        self.assertTrue(errors)
        self.assertEqual(len(self.registrations(game)), 1)
        self.assertEqual(worker.checkpoint['pending']['command'], 'execute_altering')
        game.timeout_registration = False
        resumed, errors = self.run_game(game, checkpoint=worker.checkpoint)
        self.assertTrue(errors)
        self.assertEqual(len(self.registrations(game)), 1)
        self.assertEqual(resumed.remaining, 1)


if __name__ == '__main__': unittest.main()
