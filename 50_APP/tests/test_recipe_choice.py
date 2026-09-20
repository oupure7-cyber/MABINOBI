import copy
import math
import unittest

from app.dashboard.recipe_variants import choose_recipe_variant, recipe_signature


def recipe(identity, *, produced=1, ready=False, needs=None, reason=None):
    return {"DisplayName": "시험 제작품", "RecipeId": identity,
            "ProducedPerCraft": produced, "Craftable": ready,
            "Reason": reason if reason is not None else (None if ready else "not_enough_ingredient"),
            "MissingIngredients": [{"DisplayName": name, "Required": required, "Owned": owned}
                                   for name, required, owned in (needs or [])]}


class RecipeChoiceTests(unittest.TestCase):
    def test_ready_beats_shortage_and_hard_locked_despite_yield(self):
        ready = recipe("ready", produced=1, ready=True)
        shortage = recipe("shortage", produced=10, needs=[("약초", 1, 0)])
        locked = recipe("locked", produced=10, reason="insufficient_facility_level")
        for rows in ([locked, shortage, ready], [ready, shortage, locked]):
            selected = choose_recipe_variant(rows, desired=10)
            self.assertEqual(selected["RecipeId"], "ready")
            self.assertEqual(selected["_catalog_variant_count"], 3)

    def test_actionable_shortage_beats_hard_lock(self):
        locked = recipe("locked", reason="insufficient_living_skill_level")
        actionable = recipe("actionable", needs=[("약초", 10, 0)])
        self.assertEqual(choose_recipe_variant([locked, actionable])["RecipeId"], "actionable")

    def test_obtainable_ingredients_beat_cheaper_missing_route(self):
        blocked = recipe("missing-route", produced=10, needs=[("희귀 재료", 1, 0)])
        accessible = recipe("obtainable", needs=[("약초", 20, 0)])
        def cost(name, deficit):
            return math.inf if name == "희귀 재료" else deficit
        self.assertEqual(choose_recipe_variant([blocked, accessible], material_cost=cost)["RecipeId"], "obtainable")

    def test_cost_is_actual_deficit_normalized_by_yield(self):
        low_yield = recipe("low", produced=1, needs=[("약초", 10, 9)])
        high_yield = recipe("high", produced=5, needs=[("약초", 10, 8)])
        calls = []
        def cost(name, deficit):
            calls.append((name, deficit))
            return deficit
        self.assertEqual(choose_recipe_variant([low_yield, high_yield], material_cost=cost)["RecipeId"], "high")
        self.assertCountEqual(calls, [("약초", 1), ("약초", 2)])

    def test_desired_divisibility_prefers_compatible_equally_ready_yield(self):
        incompatible = recipe("a", produced=3, ready=True)
        compatible = recipe("z", produced=5, ready=True)
        self.assertEqual(choose_recipe_variant([incompatible, compatible], desired=10)["RecipeId"], "z")

    def test_stable_input_and_shortage_order_with_preserved_variants(self):
        a = recipe("a", needs=[("약초", 2, 0), ("꽃", 3, 1)])
        b = recipe("b", needs=[("꽃", 3, 1), ("약초", 2, 0)])
        rows = [a, b]
        original = copy.deepcopy(rows)
        first = choose_recipe_variant(rows)
        second = choose_recipe_variant(list(reversed(rows)))
        self.assertEqual(first, second)
        self.assertEqual(rows, original)
        self.assertEqual(len(first["_catalog_variants"]), 2)
        self.assertEqual(recipe_signature(first), recipe_signature(a))
        first["_catalog_variants"][0]["MissingIngredients"][0]["Required"] = 999
        self.assertEqual(rows, original)

    def test_malformed_ready_record_does_not_beat_valid_shortage(self):
        malformed = recipe("bad", produced=0, ready=True)
        valid = recipe("valid", needs=[("약초", 2, 0)])
        self.assertEqual(choose_recipe_variant([malformed, valid])["RecipeId"], "valid")
        bad_owned = recipe("bad-owned", ready=True, needs=[("약초", 2, "unknown")])
        self.assertEqual(choose_recipe_variant([bad_owned, valid])["RecipeId"], "valid")

    def test_altering_and_standalone_gathering_readiness(self):
        cold = {"DisplayName": "판자", "Alterable": False, "ProducedPerWork": 3,
                "Reason": "not_enough_ingredient", "MissingIngredients": [{"DisplayName": "통나무", "Required": 2}]}
        ready = {"DisplayName": "판자", "Alterable": True, "ProducedPerWork": 3}
        self.assertTrue(choose_recipe_variant([cold, ready])["Alterable"])
        self.assertTrue(choose_recipe_variant([{"DisplayName": "풀", "ToolOk": False},
                                              {"DisplayName": "풀", "ToolOk": True}])["ToolOk"])

    def test_tool_ok_does_not_override_locked_crafting(self):
        locked = recipe("locked", reason="insufficient_facility_level")
        locked["ToolOk"] = True
        shortage = recipe("shortage", needs=[("약초", 1, 0)])
        self.assertEqual(choose_recipe_variant([locked, shortage])["RecipeId"], "shortage")

    def test_invalid_cost_treated_as_unobtainable(self):
        bad = recipe("a", needs=[("bad", 1, 0)])
        good = recipe("b", needs=[("good", 2, 0)])
        for value in (-1, math.nan, math.inf, None):
            with self.subTest(value=value):
                self.assertEqual(choose_recipe_variant([bad, good], material_cost=lambda name, count: value if name == "bad" else count)["RecipeId"], "b")

    def test_identical_records_collapse_and_empty_input_returns_none(self):
        row = recipe("one", ready=True)
        self.assertEqual(choose_recipe_variant([row, copy.deepcopy(row)])["_catalog_variant_count"], 1)
        self.assertIsNone(choose_recipe_variant([]))
        self.assertIsNone(choose_recipe_variant([None]))


if __name__ == "__main__":
    unittest.main()
