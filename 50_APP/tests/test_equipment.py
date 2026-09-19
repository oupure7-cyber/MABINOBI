import unittest
from unittest.mock import patch
from app.dashboard.equipment_crafting import EQUIPMENT_RECIPES, TOWN_EQUIPMENT, EquipmentCraftWorker
from app.dashboard.recipe_cooking import CookingError
from app.dashboard.job_queue import JOB_CATALOG, EQUIPMENT_WEEKLY_X10
from app.dashboard.modern_window import kind, quantity

class EquipmentTests(unittest.TestCase):
    def test_twelve_unique_jobs_and_repeat_quantity(self):
        specs = [s for s in JOB_CATALOG if s.key.startswith('equipment_')]
        self.assertEqual(len(specs), 12)
        self.assertEqual(len({s.key for s in specs}), 12)
        self.assertEqual({s.make_worker().recipe for s in specs}, set(EQUIPMENT_RECIPES))
        for spec in specs:
            self.assertEqual(spec.make_worker().remaining, 2)
            self.assertEqual(kind(spec), '제작')
            self.assertEqual(quantity(spec, 2), '목표 4개')

    def test_uses_returned_name_and_crafts_in_a_single_batched_call(self):
        w = EquipmentCraftWorker('론 엣지 소드S')
        row = {'DisplayName':'론 엣지소드s', 'ProducedPerCraft':1, 'Craftable':True}
        with patch.object(w, 'items', return_value=[row]), \
             patch('app.dashboard.recipe_cooking.run_cli', return_value={'status':'accepted', 'result':'completed'}) as cli:
            w.run()
        self.assertEqual(w.remaining, 0)
        cli.assert_called_once()  # target 2 in one craftCount=2 call, not two craftCount=1 calls
        self.assertEqual(cli.call_args.args[0], 'execute_crafting')
        self.assertIn('론 엣지소드s', cli.call_args.args[1])
        self.assertIn('"craftCount": 2', cli.call_args.args[1])

    def test_no_extra_equipment_when_batch_does_not_divide_target(self):
        w = EquipmentCraftWorker('사슬 갑옷 신발')
        with patch.object(w, 'items', return_value=[{'DisplayName':w.recipe,'ProducedPerCraft':3,'Craftable':True}]), patch.object(w, 'call') as cli:
            with self.assertRaises(CookingError): w.craft_one(w.recipe)
            cli.assert_not_called()

    def test_partial_failure_retains_progress_from_earlier_successful_calls(self):
        w = EquipmentCraftWorker('사슬 갑옷 신발'); blocked=[]
        w.blocked.connect(blocked.append)
        recipe_row = {'DisplayName': w.recipe, 'ProducedPerCraft': 1, 'Craftable': True}
        responses = [
            {'error': 'invalid_count', 'maxCount': 1},  # facility only allows 1 per call
            {'status': 'accepted', 'result': 'completed'},  # that 1 succeeds
            {'error': 'not_enough_ingredient'},  # the next one fails
        ]
        with patch.object(w, 'recipe_info', return_value=recipe_row), \
             patch('app.dashboard.recipe_cooking.run_cli', side_effect=responses):
            w.run()
        self.assertEqual(w.remaining, 1)
        self.assertEqual(blocked, ['not_enough_ingredient'])

    def test_ambiguous_name_does_not_select_arbitrary_recipe(self):
        w = EquipmentCraftWorker('론 엣지 소드S')
        with patch.object(w, 'items', return_value=[{'DisplayName':'론엣지소드S'}, {'DisplayName':'론 엣지소드s'}]):
            with self.assertRaises(CookingError): w.recipe_info(w.recipe)

    def test_town_equipment_covers_every_recipe_exactly_once(self):
        all_recipes = [r for recipes in TOWN_EQUIPMENT.values() for r in recipes]
        self.assertEqual(sorted(all_recipes), sorted(EQUIPMENT_RECIPES))
        self.assertEqual(len(all_recipes), len(set(all_recipes)))

    def test_weekly_x10_specs_exist_for_every_recipe_and_stay_out_of_the_catalog(self):
        self.assertEqual(set(EQUIPMENT_WEEKLY_X10), set(EQUIPMENT_RECIPES))
        catalog_keys = {s.key for s in JOB_CATALOG}
        for recipe, spec in EQUIPMENT_WEEKLY_X10.items():
            worker = spec.make_worker()
            self.assertEqual(worker.recipe, recipe)
            self.assertEqual(worker.remaining, 10)
            self.assertNotIn(spec.key, catalog_keys)
