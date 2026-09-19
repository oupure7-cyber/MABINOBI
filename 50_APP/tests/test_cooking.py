import unittest
from unittest.mock import patch
from app.dashboard.recipe_cooking import RecipeCookingWorker, CookingError, RECIPES
from app.dashboard.job_queue import JOB_CATALOG
from app.dashboard.modern_window import kind

class CookingTests(unittest.TestCase):
    def test_all_nine_recipes_have_ten_and_fifty_targets(self):
        specs = [s for s in JOB_CATALOG if s.key.startswith('cooking_')]
        self.assertEqual(len(specs), 18)
        for s in specs:
            w = s.make_worker()
            self.assertIn(w.recipe, RECIPES)
            self.assertIn(w.remaining, (10, 50))
            self.assertEqual(kind(s), '요리')

    def test_live_missing_ingredients_then_craft_exact_returned_name(self):
        owned = 0
        commands = []
        def cli(cmd, body=None, timeout=30):
            nonlocal owned
            commands.append((cmd, body))
            if cmd == 'get_craftable_items':
                return {'items': [{'DisplayName': '호박수프', 'ProducedPerCraft': 2,
                    'Craftable': owned >= 3, 'Reason': 'not_enough_ingredient',
                    'MissingIngredients': [{'DisplayName':'호박', 'Required':3, 'Owned':owned}]}]}
            if cmd == 'get_items': return [{'DisplayName':'호박','Count':owned}]
            if cmd == 'get_gatherable_items': return {'items':[{'DisplayName':'호박','ToolOk':True}]}
            if cmd == 'execute_gathering':
                owned = 100
                return {'status':'accepted','result':'completed'}
            if cmd == 'execute_crafting': return {'status':'accepted','result':'completed'}
            raise AssertionError(cmd)
        with patch('app.dashboard.recipe_cooking.run_cli', cli):
            w = RecipeCookingWorker('호박 수프', 3)
            w.run()
            self.assertEqual(w.remaining, 0)
        crafts = [b for c,b in commands if c == 'execute_crafting']
        self.assertEqual(len(crafts), 2)
        self.assertIn('호박수프', crafts[0])

    def test_failure_preserves_remaining_after_completed_batches(self):
        w = RecipeCookingWorker('호박 수프', 10); messages=[]
        w.blocked.connect(messages.append)
        with patch.object(w, 'craft_one', side_effect=[2, CookingError('재료 부족')]): w.run()
        self.assertEqual(w.remaining, 8)
        self.assertEqual(messages, ['재료 부족'])

    def test_stopped_craft_is_not_success(self):
        w = RecipeCookingWorker('호박 수프', 10)
        with patch.object(w, 'recipe_info', return_value={'DisplayName':'호박수프', 'ProducedPerCraft':1, 'Craftable':True}), patch.object(w, 'call', return_value={'status':'accepted','result':'stopped_by_user'}):
            with self.assertRaises(CookingError): w.craft_one(w.recipe)

    def test_game_off_blocks_without_actions(self):
        w = RecipeCookingWorker('호박 수프', 10); messages=[]
        w.blocked.connect(messages.append)
        with patch('app.dashboard.recipe_cooking.run_cli', return_value={'pipe':'disconnected','reason':'game_off'}) as cli:
            w.run()
            self.assertEqual(cli.call_count, 1)
        self.assertEqual(w.remaining, 10)
        self.assertEqual(messages, ['game_off'])

    def test_fishing_stops_when_required_amount_is_available(self):
        w = RecipeCookingWorker('농어 매운탕', 10)
        with patch.object(w, 'owned', side_effect=[0, 3, 3]), patch.object(w, 'items', return_value=[{'DisplayName':'농어','ToolOk':True}]), patch.object(w, 'call', return_value={'status':'accepted','result':'started'}), patch('app.dashboard.recipe_cooking.run_cli', return_value={'status':'accepted'}) as cli:
            w.ensure('농어', 3, ())
            cli.assert_called_once_with('stop_action', timeout=30)

    def test_locked_recipe_does_not_gather_or_craft(self):
        w = RecipeCookingWorker('호박 수프', 10)
        with patch.object(w, 'recipe_info', return_value={'ProducedPerCraft':1, 'Craftable':False, 'Reason':'insufficient_living_skill_level'}), patch.object(w, 'call') as cli:
            with self.assertRaises(CookingError): w.craft_one(w.recipe)
            cli.assert_not_called()
