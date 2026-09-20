import copy
import json
import unittest
from unittest.mock import patch

from app.dashboard.crafting_engine import CraftingWorker
from app.dashboard.recipe_variants import distinct_recipe_variants, recipe_signature


class Game:
    """A deterministic connector: no real game calls are made by these tests."""
    def __init__(self, crafts, altering=None, gather=(), owned=None):
        self.crafts, self.altering = crafts, altering or {}
        self.gather, self.owned = set(gather), dict(owned or {})
        self.actions, self.works = [], []
        self.complete_immediately = True
        self.gather_amount = 100
        self.craft_results = []

    def rows(self, recipes, altering=False):
        rows = []
        for name, spec in recipes.items():
            missing = [{"DisplayName": n, "Required": q, "Owned": self.owned.get(n, 0)}
                       for n, q in spec.get("ingredients", {}).items() if self.owned.get(n, 0) < q]
            rows.append({"DisplayName": name, "Alterable" if altering else "Craftable": not missing,
                         "ProducedPerWork" if altering else "ProducedPerCraft": spec.get("produced", 1),
                         "Reason": "not_enough_ingredient" if missing else None,
                         "MissingIngredients": missing})
        return {"items": rows}

    def __call__(self, cmd, body=None, timeout=30):
        args = json.loads(body) if body else {}
        if cmd == "get_craftable_items": return self.rows(self.crafts)
        if cmd == "get_alterable_items": return self.rows(self.altering, True)
        if cmd == "get_gatherable_items": return {"items": [{"DisplayName": n, "ToolOk": True} for n in self.gather]}
        if cmd == "get_items": return [{"DisplayName": args["name"], "Count": self.owned.get(args["name"], 0)}]
        if cmd == "get_altering_works":
            return {"works": [{"DisplayName": n, "FacilityName": "시설", "IsCompleted": self.complete_immediately,
                               "State": "Completed" if self.complete_immediately else "InProgress",
                               "RemainingSeconds": 0 if self.complete_immediately else 10} for n in self.works]}
        self.actions.append((cmd, args, dict(self.owned)))
        if cmd == "execute_gathering":
            name = args["displayName"]
            self.owned[name] = self.owned.get(name, 0) + self.gather_amount
            return {"status": "accepted", "result": "completed"}
        if cmd == "execute_crafting":
            if self.craft_results:
                result = self.craft_results.pop(0)
                if result.get("result") != "completed": return result
            spec = self.crafts[args["displayName"]]
            assert args["craftCount"] == 1
            self.consume(spec)
            name = spec.get("output", args["displayName"])
            self.owned[name] = self.owned.get(name, 0) + spec.get("produced", 1)
            return {"status": "accepted", "result": "completed", "craftCount": 1}
        if cmd == "execute_altering":
            self.consume(self.altering[args["displayName"]])
            self.works.append(args["displayName"])
            return {"status": "accepted", "result": "started"}
        if cmd == "complete_altering_work":
            count = len(self.works)
            for recipe in self.works:
                spec = self.altering[recipe]
                name = spec.get("output", recipe)
                self.owned[name] = self.owned.get(name, 0) + spec.get("produced", 1)
            self.works = []
            return {"status": "accepted", "collected": count}
        if cmd == "stop_action": return {"status": "accepted"}
        raise AssertionError(cmd)

    def consume(self, spec):
        for n, q in spec.get("ingredients", {}).items():
            assert self.owned.get(n, 0) >= q, f"Missing {n}"
            self.owned[n] -= q


class CraftingEngineTests(unittest.TestCase):
    def run_worker(self, game, name="검", count=3, checkpoint=None):
        w = CraftingWorker(name, count)
        if checkpoint is not None: w.checkpoint = copy.deepcopy(checkpoint)
        messages, progress = [], []
        w.blocked.connect(messages.append)
        w.progress.connect(progress.append)
        with patch("app.dashboard.crafting_engine.run_cli", game): w.run()
        return w, messages, progress

    def test_known_total_ingredients_prepared_before_first_craft(self):
        game = Game({"검": {"ingredients": {"광석": 4}}}, gather=("광석",))
        game.gather_amount = 1
        w, errors, progress = self.run_worker(game)
        self.assertEqual(errors, [])
        crafts = [a for a in game.actions if a[0] == "execute_crafting"]
        self.assertEqual(crafts[0][2]["광석"], 12)
        self.assertEqual(len(crafts), 3)
        self.assertEqual(w.remaining, 0)
        self.assertEqual(w.checkpoint["completed"], 3)
        self.assertEqual(progress[-1]["stage"], "완료")

    def test_nested_altering_alias_and_collection_before_final(self):
        game = Game({"검": {"ingredients": {"강철괴": 2}}}, {
            "강철괴": {"ingredients": {"철괴": 3, "석탄": 4}, "produced": 3},
            "철괴(철 광석)": {"ingredients": {"철 광석": 10}, "produced": 3, "output": "철괴"},
        }, gather=("철 광석", "석탄"))
        w, errors, _ = self.run_worker(game)
        self.assertEqual(errors, [])
        first_craft = next(a for a in game.actions if a[0] == "execute_crafting")
        self.assertEqual(first_craft[2]["강철괴"], 6)
        alterations = [a[1]["displayName"] for a in game.actions if a[0] == "execute_altering"]
        self.assertCountEqual(alterations, ["철괴(철 광석)"] * 2 + ["강철괴"] * 2)
        for action, args, stock in game.actions:
            if action == "execute_altering" and args["displayName"] == "강철괴":
                self.assertGreaterEqual(stock.get("철괴", 0), 3)
                self.assertGreaterEqual(stock.get("석탄", 0), 4)
        self.assertEqual(w.remaining, 0)

    def test_known_intermediate_shortages_preserve_final_reserves(self):
        game = Game({"검": {"ingredients": {"목재": 3, "판자": 2}}},
                    {"판자": {"ingredients": {"목재": 2}}}, gather=("목재",))
        game.gather_amount = 1
        w, errors, _ = self.run_worker(game, count=2)
        self.assertEqual(errors, [])
        first_craft = next(a for a in game.actions if a[0] == "execute_crafting")
        self.assertEqual(first_craft[2]["목재"], 6)
        self.assertEqual(first_craft[2]["판자"], 4)
        self.assertEqual(w.remaining, 0)

    def test_unknown_material_requires_manual_preparation(self):
        game = Game({"검": {"ingredients": {"희귀 가죽": 2}}})
        w, errors, _ = self.run_worker(game)
        self.assertEqual(game.actions, [])
        self.assertIn("직접 준비", errors[0])
        self.assertEqual(w.remaining, 3)

    def test_recursive_cycle_has_no_actions(self):
        game = Game({"검": {"ingredients": {"중간재": 1}}, "중간재": {"ingredients": {"검": 1}}})
        _, errors, _ = self.run_worker(game)
        self.assertIn("순환", errors[0])
        self.assertEqual(game.actions, [])

    def test_exact_names_only_and_exact_output_target(self):
        game = Game({"정밀 검": {"produced": 2}})
        _, errors, _ = self.run_worker(game, name="정밀검", count=4)
        self.assertIn("정확한 이름", errors[0])
        _, errors, _ = self.run_worker(game, name="정밀 검", count=3)
        self.assertIn("배수", errors[0])
        self.assertEqual(game.actions, [])

    def test_uncertain_craft_retains_progress_and_prevents_duplicate_on_resume(self):
        game = Game({"검": {}})
        game.craft_results = [{"result": "completed"}, {"error": "timeout"}]
        w, errors, _ = self.run_worker(game)
        self.assertEqual(w.remaining, 2)
        self.assertEqual(w.checkpoint["completed"], 1)
        self.assertIn("미확인", errors[0])
        before = len(game.actions)
        resumed, errors, _ = self.run_worker(game, checkpoint=w.checkpoint)
        self.assertEqual(len(game.actions), before)
        self.assertEqual(resumed.remaining, 2)
        self.assertIn("중복 제작", errors[0])

    def test_explicit_rejection_can_resume_without_duplicate_completed_work(self):
        game = Game({"검": {}})
        game.craft_results = [{"result": "completed"}, {"status": "rejected", "error": "not_enough_currency"}]
        w, errors, _ = self.run_worker(game)
        self.assertIsNone(w.checkpoint["pending"])
        self.assertEqual(w.remaining, 2)
        resumed, errors, _ = self.run_worker(game, checkpoint=w.checkpoint)
        self.assertEqual(errors, [])
        self.assertEqual(resumed.remaining, 0)
        self.assertEqual(game.owned["검"], 3)

    def test_pause_while_processing_resumes_existing_work(self):
        game = Game({"검": {"ingredients": {"목재": 1}}}, {"목재": {}})
        game.complete_immediately = False
        w = CraftingWorker("검", 1)
        errors = []; w.blocked.connect(errors.append)
        with patch("app.dashboard.crafting_engine.run_cli", game), patch.object(w, "_sleep", side_effect=lambda _: w.request_stop()):
            w.run()
        self.assertEqual(errors, [])
        self.assertIsNotNone(w.checkpoint["waiting"])
        self.assertEqual(w.remaining, 1)
        game.complete_immediately = True
        resumed, errors, _ = self.run_worker(game, count=1, checkpoint=w.checkpoint)
        self.assertEqual(errors, [])
        self.assertEqual(resumed.remaining, 0)
        self.assertEqual(sum(a[0] == "execute_altering" for a in game.actions), 1)

    def test_queued_work_can_wait_behind_long_facility_job(self):
        game = Game({}, {"목재": {}})
        game.complete_immediately = False
        game.works = ["목재"]
        w = CraftingWorker("검", 1)
        waiting = {"product": "목재", "recipe": "목재", "before": 0, "required": 1}
        w.checkpoint["waiting"] = waiting
        slept = []
        def sleep(_):
            slept.append(True)
            if len(slept) == 2: game.complete_immediately = True
        def cli(cmd, body=None, timeout=30):
            result = game(cmd, body, timeout)
            if cmd == "get_altering_works" and not game.complete_immediately:
                result["works"][0].update(State="NotStarted", RemainingSeconds=0)
            return result
        with patch("app.dashboard.crafting_engine.run_cli", cli), patch.object(w, "_sleep", side_effect=sleep), \
             patch("app.dashboard.crafting_engine.time.monotonic", side_effect=[0, 1, 2, 700, 701]):
            w._wait_altering(waiting)
        self.assertEqual(game.owned["목재"], 1)
        self.assertIsNone(w.checkpoint["waiting"])

    def test_fishing_stop_is_called_even_on_pause(self):
        w = CraftingWorker("생선 요리", 1)
        commands = []
        def cli(cmd, body=None, timeout=30):
            commands.append(cmd)
            if cmd == "execute_gathering": return {"status": "accepted", "result": "started"}
            if cmd == "stop_action": return {"status": "accepted"}
            if cmd == "get_items": return [{"DisplayName": "농어", "Count": 0}]
            raise AssertionError(cmd)
        with patch("app.dashboard.crafting_engine.run_cli", cli), patch.object(w, "_sleep", side_effect=lambda _: w.request_stop()):
            with self.assertRaises(Exception): w._gather("농어", 0, 1)
        self.assertEqual(commands[-1], "stop_action")
        self.assertIsNone(w.checkpoint["fishing"])

    def test_fishing_success_waits_for_required_count_and_stops(self):
        w = CraftingWorker("생선 요리", 1)
        counts = iter((0, 1, 3))
        commands = []
        def cli(cmd, body=None, timeout=30):
            commands.append(cmd)
            if cmd == "execute_gathering": return {"status": "accepted", "result": "started"}
            if cmd == "stop_action": return {"status": "accepted"}
            if cmd == "get_items": return [{"DisplayName": "농어", "Count": next(counts)}]
            raise AssertionError(cmd)
        with patch("app.dashboard.crafting_engine.run_cli", cli), patch.object(w, "_sleep"):
            w._gather("농어", 0, 3)
        self.assertEqual(commands.count("get_items"), 3)
        self.assertEqual(commands.count("stop_action"), 1)

    def test_already_stopped_fishing_does_not_block_resume_forever(self):
        game = Game({"검": {}})
        def cli(cmd, body=None, timeout=30):
            if cmd == "stop_action":
                return {"status": "rejected", "error": "invalid_state"}
            return game(cmd, body, timeout)
        checkpoint = CraftingWorker("검", 1).checkpoint
        checkpoint["fishing"] = "농어"
        w, errors, _ = self.run_worker(cli, count=1, checkpoint=checkpoint)
        self.assertEqual(errors, [])
        self.assertIsNone(w.checkpoint["fishing"])
        self.assertEqual(w.remaining, 0)

    def test_unconfirmed_fishing_stop_stays_blocked(self):
        checkpoint = CraftingWorker("검", 1).checkpoint
        checkpoint["fishing"] = "농어"
        w, errors, _ = self.run_worker(lambda *a, **k: {"error": "timeout"}, count=1, checkpoint=checkpoint)
        self.assertIn("낚시 정지", errors[0])
        self.assertEqual(w.checkpoint["fishing"], "농어")
        self.assertEqual(w.remaining, 1)

    def test_collection_timeout_keeps_pending_and_never_requeues(self):
        game = Game({"검": {"ingredients": {"목재": 1}}}, {"목재": {}})
        def cli(cmd, body=None, timeout=30):
            if cmd == "complete_altering_work": return {"error": "timeout"}
            return game(cmd, body, timeout)
        w, errors, _ = self.run_worker(cli, count=1)
        self.assertIn("미확인", errors[0])
        self.assertEqual(w.checkpoint["pending"]["command"], "complete_altering_work")
        before = len(game.actions)
        resumed, errors, _ = self.run_worker(cli, count=1, checkpoint=w.checkpoint)
        self.assertEqual(len(game.actions), before)
        self.assertEqual(resumed.remaining, 1)

    def test_output_count_uses_produced_per_craft_not_number_of_calls(self):
        game = Game({"검": {"produced": 3}})
        w, errors, _ = self.run_worker(game, count=6)
        self.assertEqual(errors, [])
        self.assertEqual(w.remaining, 0)
        self.assertEqual(len(game.actions), 2)

    def test_pause_after_confirmed_craft_records_that_completion(self):
        game = Game({"검": {}})
        w = CraftingWorker("검", 3)
        def cli(cmd, body=None, timeout=30):
            result = game(cmd, body, timeout)
            if cmd == "execute_crafting": w.request_stop()
            return result
        with patch("app.dashboard.crafting_engine.run_cli", cli): w.run()
        self.assertEqual(w.remaining, 2)
        self.assertEqual(w.checkpoint["completed"], 1)
        self.assertIsNone(w.checkpoint["pending"])

    def test_gather_with_no_inventory_increase_blocks(self):
        game = Game({"검": {"ingredients": {"광석": 1}}}, gather=("광석",))
        game.gather_amount = 0
        _, errors, _ = self.run_worker(game, count=1)
        self.assertIn("늘지 않아", errors[0])
        self.assertEqual(len(game.actions), 1)

    def test_locked_inventory_not_counted_and_game_off_no_actions(self):
        w = CraftingWorker("검", 1)
        with patch("app.dashboard.crafting_engine.run_cli", return_value=[
            {"DisplayName": "광석", "Count": 999, "IsLocked": True},
            {"DisplayName": "광석", "Count": 2, "Location": "account_storage"},
            {"DisplayName": "광석", "Count": 3, "Location": "inventory"},
        ]): self.assertEqual(w._owned("광석"), 5)
        errors = []; w.blocked.connect(errors.append)
        with patch("app.dashboard.crafting_engine.run_cli", return_value={"pipe": "disconnected", "reason": "game_off"}) as cli:
            w.run()
            self.assertEqual(cli.call_count, 1)
        self.assertEqual(w.remaining, 1)
        self.assertIn("game_off", errors[0])

    def test_conditions_block_before_gathering_and_progress_is_independent(self):
        w = CraftingWorker("검", 1)
        errors = []; w.blocked.connect(errors.append)
        with patch("app.dashboard.crafting_engine.run_cli", return_value={"items": [{"DisplayName": "검", "ProducedPerCraft": 1,
                "Craftable": False, "Reason": "insufficient_facility_level"}]}) as cli:
            w.run()
            self.assertTrue(all(c.args[0] == "get_craftable_items" for c in cli.call_args_list))
        self.assertIn("시설 레벨", errors[0])

    def test_unrelated_same_name_variants_do_not_block_consumable(self):
        game = Game({"회복 물약": {"produced": 5}})
        def cli(cmd, body=None, timeout=30):
            response = game(cmd, body, timeout)
            if cmd == "get_craftable_items":
                response["items"].extend([
                    {"DisplayName": "최상급 붕대", "ProducedPerCraft": 10, "Craftable": True},
                    {"DisplayName": "최상급 붕대", "ProducedPerCraft": 5, "Craftable": True},
                ])
            return response
        w, errors, _ = self.run_worker(cli, name="회복 물약", count=10)
        self.assertEqual(errors, [])
        self.assertEqual(w.remaining, 0)
        self.assertEqual(game.owned["회복 물약"], 10)
        self.assertEqual(len(game.actions), 2)

    def test_equivalent_repeated_shortages_allow_gather_then_craft(self):
        # Synthetic ingredients intentionally avoid asserting a real game recipe.
        game = Game({"회복 물약": {"produced": 5,
                    "ingredients": {"시험 약초": 2, "시험 꽃": 1}}},
                    gather=("시험 약초", "시험 꽃"))
        def cli(cmd, body=None, timeout=30):
            response = game(cmd, body, timeout)
            if cmd == "get_craftable_items":
                repeated = copy.deepcopy(response["items"][0])
                repeated["MissingIngredients"].reverse()
                repeated["_catalog_variant_count"] = 2
                response["items"].append(repeated)
            return response
        w, errors, _ = self.run_worker(cli, name="회복 물약", count=5)
        self.assertEqual(errors, [])
        self.assertEqual(w.remaining, 0)
        self.assertEqual(game.owned["회복 물약"], 5)
        self.assertEqual(sum(action[0] == "execute_crafting" for action in game.actions), 1)

    def test_different_same_name_yields_use_actual_output(self):
        game = Game({"최상급 붕대": {"produced": 10,
                    "ingredients": {"시험 옷감": 2}}}, gather=("시험 옷감",))
        def cli(cmd, body=None, timeout=30):
            response = game(cmd, body, timeout)
            if cmd == "get_craftable_items":
                repeated = copy.deepcopy(response["items"][0])
                repeated["ProducedPerCraft"] = 5
                response["items"].append(repeated)
            return response
        w, errors, _ = self.run_worker(cli, name="최상급 붕대", count=10)
        self.assertEqual(errors, [])
        self.assertEqual(w.remaining, 0)
        self.assertEqual(game.owned["최상급 붕대"], 10)
        self.assertEqual(sum(action[0] == "execute_crafting" for action in game.actions), 1)
        self.assertIsNone(w.checkpoint["pending"])

    def test_different_same_name_ingredients_prepare_available_route_only(self):
        game = Game({"밀봉된 저주 해제 물약 상자": {"ingredients": {"시험 약초": 2}}},
                    gather=("시험 약초",))
        def cli(cmd, body=None, timeout=30):
            response = game(cmd, body, timeout)
            if cmd == "get_craftable_items":
                repeated = copy.deepcopy(response["items"][0])
                repeated["Craftable"] = False
                repeated["Reason"] = "not_enough_ingredient"
                repeated["MissingIngredients"] = [{"DisplayName": "시험 꽃", "Required": 2, "Owned": 0}]
                response["items"].append(repeated)
            return response
        _, errors, _ = self.run_worker(cli, name="밀봉된 저주 해제 물약 상자", count=1)
        self.assertEqual(errors, [])
        gathered = [action[1]["displayName"] for action in game.actions if action[0] == "execute_gathering"]
        self.assertEqual(gathered, ["시험 약초"])
        self.assertEqual(game.owned["밀봉된 저주 해제 물약 상자"], 1)

    def test_internal_identity_difference_is_not_discarded(self):
        rows = [{"DisplayName": "상자", "ProducedPerCraft": 1, "Craftable": True,
                 "RecipeId": recipe_id} for recipe_id in (101, 102)]
        self.assertEqual(len(distinct_recipe_variants(rows)), 2)
        game = Game({"상자": {}})
        def cli(cmd, body=None, timeout=30):
            if cmd == "get_craftable_items": return {"items": copy.deepcopy(rows)}
            return game(cmd, body, timeout)
        _, errors, _ = self.run_worker(cli, name="상자", count=1)
        self.assertEqual(errors, [])
        self.assertEqual(len(game.actions), 1)
        self.assertEqual(game.actions[0][1], {"displayName": "상자", "craftCount": 1})

    def test_duplicate_signature_preserves_quantities_conditions_and_types(self):
        row = {"DisplayName": "시험약", "ProducedPerCraft": 5, "Craftable": False,
               "Reason": "not_enough_ingredient", "ToolOk": True,
               "MissingIngredients": [{"DisplayName": "시험재료", "Required": 2, "Owned": 0}]}
        for field, value in (("ProducedPerCraft", 10), ("Craftable", True),
                             ("Reason", "ingredient_locked"), ("ToolOk", False),
                             ("ToolOk", 1), ("UnknownRecipeIdentity", "second")):
            with self.subTest(field=field, value=value):
                variant = {**row, field: value}
                self.assertNotEqual(recipe_signature(row), recipe_signature(variant))
        for field, value in (("Required", 3), ("Owned", 1)):
            variant = copy.deepcopy(row)
            variant["MissingIngredients"][0][field] = value
            self.assertNotEqual(recipe_signature(row), recipe_signature(variant))

    def test_consumable_recursively_gathers_processes_collects_and_crafts(self):
        # Every ingredient and quantity below is synthetic test data, not a game
        # recipe claim. Only the target name is from the user's screenshot.
        game = Game({
            "상급 자동회복 물약": {"produced": 5, "ingredients": {"시험용 농축액": 2}},
            "시험용 농축액": {"ingredients": {"시험용 추출물": 1}},
        }, {"시험용 추출물": {"ingredients": {"시험용 약초": 3}, "produced": 2}},
                    gather=("시험용 약초",))
        w, errors, progress = self.run_worker(game, name="상급 자동회복 물약", count=10)
        self.assertEqual(errors, [])
        self.assertEqual(w.remaining, 0)
        self.assertEqual(game.owned["상급 자동회복 물약"], 10)
        commands = [action[0] for action in game.actions]
        self.assertEqual(commands[0], "execute_gathering")
        first_alter = commands.index("execute_altering")
        first_collect = commands.index("complete_altering_work")
        first_intermediate = next(index for index, action in enumerate(game.actions)
                                  if action[0] == "execute_crafting")
        first_final = next(index for index, action in enumerate(game.actions)
                          if action[0] == "execute_crafting" and
                          action[1]["displayName"] == "상급 자동회복 물약")
        self.assertLess(first_alter, first_collect)
        self.assertLess(first_collect, first_intermediate)
        self.assertLess(first_intermediate, first_final)
        self.assertEqual(game.actions[first_final][2]["시험용 농축액"], 4)
        self.assertTrue({"채집", "가공", "생산물 회수", "제작", "완료"}.issubset(
            {event["stage"] for event in progress}))


if __name__ == "__main__":
    unittest.main()
