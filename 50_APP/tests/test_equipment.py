import unittest
from unittest.mock import patch
from app.dashboard.equipment_crafting import EQUIPMENT_RECIPES, EquipmentCraftWorker
from app.dashboard.recipe_cooking import CookingError
from app.dashboard.job_queue import JOB_CATALOG
from app.dashboard.modern_window import kind, quantity

class EquipmentTests(unittest.TestCase):
    def test_twelve_unique_jobs_and_repeat_quantity(self):
        specs = [s for s in JOB_CATALOG if s.key.startswith('equipment_')]
        self.assertEqual(len(specs), 12)
        self.assertEqual(len({s.key for s in specs}), 12)
        self.assertEqual({s.make_worker().recipe for s in specs}, set(EQUIPMENT_RECIPES))
        for spec in specs:
            self.assertEqual(spec.make_worker().remaining, 3)
            self.assertEqual(kind(spec), '제작')
            self.assertEqual(quantity(spec, 2), '목표 6개')

    def test_uses_returned_name_and_crafts_three(self):
        w = EquipmentCraftWorker('론 엣지 소드S')
        row = {'DisplayName':'론 엣지소드s', 'ProducedPerCraft':1, 'Craftable':True}
        with patch.object(w, 'items', return_value=[row]), patch.object(w, 'call', return_value={'status':'accepted', 'result':'completed'}) as cli:
            w.run()
        self.assertEqual(w.remaining, 0)
        self.assertEqual(cli.call_count, 3)
        for call in cli.call_args_list:
            self.assertIn('론 엣지소드s', call.args[1])

    def test_no_extra_equipment_when_batch_does_not_divide_target(self):
        w = EquipmentCraftWorker('사슬 갑옷 신발')
        with patch.object(w, 'items', return_value=[{'DisplayName':w.recipe,'ProducedPerCraft':2,'Craftable':True}]), patch.object(w, 'call') as cli:
            with self.assertRaises(CookingError): w.craft_one(w.recipe)
            cli.assert_not_called()

    def test_partial_failure_retains_two_remaining(self):
        w = EquipmentCraftWorker('사슬 갑옷 신발'); blocked=[]
        w.blocked.connect(blocked.append)
        with patch.object(w, 'craft_one', side_effect=[1, CookingError('재료 부족')]): w.run()
        self.assertEqual(w.remaining, 2)
        self.assertEqual(blocked, ['재료 부족'])

    def test_ambiguous_name_does_not_select_arbitrary_recipe(self):
        w = EquipmentCraftWorker('론 엣지 소드S')
        with patch.object(w, 'items', return_value=[{'DisplayName':'론엣지소드S'}, {'DisplayName':'론 엣지소드s'}]):
            with self.assertRaises(CookingError): w.recipe_info(w.recipe)
