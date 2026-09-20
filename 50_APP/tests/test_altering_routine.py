"""Run: python -m unittest discover -s tests (no game CLI calls).

Covers the 2026-09-20 N-tier redesign: the FAMILIES data model (matches
10_RESEARCH/05_altering_full_recipe_chains_2026-09-20.md) and the promotion/reserve rule in
_plan_one_slot, both pure logic with no CLI/Qt-window dependency.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.dashboard.altering_routine import FAMILIES, QUEUE_CAPACITY, PROMOTION_MARGIN, AlteringRoutineWorker


def family(key):
    return next(f for f in FAMILIES if f.key == key)


class FamilyDataTests(unittest.TestCase):
    def test_four_families_seven_tiers_each(self):
        self.assertEqual({f.key for f in FAMILIES}, {'metal', 'wood', 'leather', 'cloth'})
        for f in FAMILIES:
            self.assertEqual(len(f.tiers), 7, f.key)

    def test_default_target_matches_the_old_fixed_end_product(self):
        # 강철괴/목재+/가죽+/옷감+ - the old hardcoded ceiling - must stay the default so
        # existing behavior doesn't silently change until a user actually drags a slider.
        expected = {'metal': '강철괴', 'wood': '목재+', 'leather': '가죽+', 'cloth': '옷감+'}
        for f in FAMILIES:
            self.assertEqual(f.tiers[f.default_target_idx].name, expected[f.key])

    def test_only_tier_zero_has_more_than_one_recipe_option(self):
        for f in FAMILIES:
            for idx, tier in enumerate(f.tiers):
                if f.key == 'metal' and idx == 0:
                    self.assertEqual(len(tier.recipes), 2)
                else:
                    self.assertEqual(len(tier.recipes), 1, f'{f.key} tier {idx}')

    def test_previous_tier_ingredient_names_match_the_tier_below(self):
        for f in FAMILIES:
            for idx in range(1, len(f.tiers)):
                for option in f.tiers[idx].recipes:
                    prev_ings = [ing for ing in option.inputs if ing.is_previous_tier]
                    self.assertEqual(len(prev_ings), 1, f'{f.key} tier {idx}')
                    self.assertEqual(prev_ings[0].material, f.tiers[idx - 1].name)

    def test_n_m_k_progression_matches_research_doc_from_tier_three_onward(self):
        # tier index 2..6 (합금강괴류 이상): N=3,4,5,5,5 / M=15,20,20,20,20 / K=8,12,16,20,20 -
        # identical across all four families (10_RESEARCH/05, "구조적 패턴" 표).
        expected_n = [3, 4, 5, 5, 5]
        expected_m = [15, 20, 20, 20, 20]
        expected_k = [8, 12, 16, 20, 20]
        for f in FAMILIES:
            for offset, idx in enumerate(range(2, 7)):
                option = f.tiers[idx].recipes[0]
                prev = next(i for i in option.inputs if i.is_previous_tier)
                others = [i for i in option.inputs if not i.is_previous_tier]
                self.assertEqual(prev.qty, expected_n[offset], f'{f.key} tier {idx} N')
                self.assertEqual({i.qty for i in others}, {expected_m[offset], expected_k[offset]}, f'{f.key} tier {idx} M/K')

    def test_leather_tannin_and_rawhide_are_not_gatherable(self):
        leather = family('leather')
        for tier in leather.tiers:
            for option in tier.recipes:
                for ing in option.inputs:
                    if not ing.is_previous_tier:
                        self.assertFalse(ing.gatherable, ing.material)

    def test_leather_skip_below_rule_is_generic_now(self):
        leather = family('leather')
        self.assertEqual(leather.skip_below, ('생가죽', 10))
        for f in FAMILIES:
            if f.key != 'leather':
                self.assertIsNone(f.skip_below)


class PlanOneSlotTests(unittest.TestCase):
    def setUp(self):
        self.worker = AlteringRoutineWorker()
        self.metal = family('metal')

    def _threshold(self, n):
        return n * QUEUE_CAPACITY + PROMOTION_MARGIN  # 5

    def test_target_tier_itself_has_no_cap_on_its_own_stock(self):
        # target=강철괴(1) with only enough 철괴/석탄 for exactly one work (no huge surplus) -
        # still produces it; being the target never blocks producing more of itself.
        local = {'철괴': self._threshold(3) + 3, '석탄': 4}
        step = self.worker._plan_one_slot(self.metal, local, target_idx=1)
        self.assertIsNotNone(step)
        display_name, _log, consumption = step
        self.assertEqual(display_name, '강철괴')
        self.assertEqual(consumption, {'철괴': 3, '석탄': 4})

    def test_below_reserve_blocks_promotion_and_falls_back_a_tier(self):
        # target=합금강괴(2), but 강철괴 stock is below its reserve (3*7+5=26, need 29 to spare
        # 3) - must NOT spend it on 합금강괴, must fall back to making more 강철괴 instead.
        local = {'강철괴': 25, '동 광석': 100, '석탄': 100, '철괴': 100}
        step = self.worker._plan_one_slot(self.metal, local, target_idx=2)
        self.assertIsNotNone(step)
        display_name, _log, consumption = step
        self.assertEqual(display_name, '강철괴')
        self.assertEqual(consumption, {'철괴': 3, '석탄': 4})

    def test_excess_above_reserve_promotes_to_the_target_tier(self):
        # Same as above but 강철괴 now clears the reserve+need bar (>= 26+3=29) - should
        # promote to 합금강괴 instead of falling back.
        local = {'강철괴': 29, '동 광석': 100, '석탄': 100, '철괴': 100}
        step = self.worker._plan_one_slot(self.metal, local, target_idx=2)
        self.assertIsNotNone(step)
        display_name, _log, consumption = step
        self.assertEqual(display_name, '합금강괴')
        self.assertEqual(consumption, {'강철괴': 3, '동 광석': 15, '석탄': 8})

    def test_cascades_all_the_way_down_to_tier_zero_when_everything_above_is_blocked(self):
        local = {'철괴': 100, '철 광석': 100, '광석': 100, '석탄': 0, '강철괴': 0, '동 광석': 0}
        step = self.worker._plan_one_slot(self.metal, local, target_idx=2)
        self.assertIsNotNone(step)
        display_name, _log, consumption = step
        self.assertIn(display_name, ('철괴(철 광석)', '철괴(광석)'))
        self.assertNotIn('강철괴', consumption)

    def test_returns_none_when_nothing_is_craftable(self):
        local = {'철괴': 0, '철 광석': 0, '광석': 0, '석탄': 0}
        self.assertIsNone(self.worker._plan_one_slot(self.metal, local, target_idx=2))

    def test_plan_fill_stops_at_free_slots_without_mutating_the_callers_dict(self):
        inv = {'철괴': self._threshold(3) + 3 * 3, '석탄': 4 * 3}
        inv_before = dict(inv)
        plan = self.worker._plan_fill(self.metal, inv, free_slots=3, target_idx=1)
        self.assertEqual(len(plan), 3)
        total_consumed: dict[str, int] = {}
        for _name, _log, consumption in plan:
            for material, qty in consumption.items():
                total_consumed[material] = total_consumed.get(material, 0) + qty
        self.assertEqual(total_consumed, {'철괴': 9, '석탄': 12})
        self.assertEqual(inv, inv_before)  # _plan_fill only mutates its own scratch copy


class TargetStorageTests(unittest.TestCase):
    def test_default_targets_match_each_familys_default_idx(self):
        worker = AlteringRoutineWorker()
        for f in FAMILIES:
            self.assertEqual(worker._target_for(f.key), f.default_target_idx)

    def test_set_target_takes_effect_immediately(self):
        worker = AlteringRoutineWorker()
        worker.set_target('metal', 4)
        self.assertEqual(worker._target_for('metal'), 4)
        # other families untouched
        self.assertEqual(worker._target_for('wood'), family('wood').default_target_idx)


if __name__ == '__main__':
    unittest.main()
