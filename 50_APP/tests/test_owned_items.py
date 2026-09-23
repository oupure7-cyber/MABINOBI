"""Offline tests for carried/warehouse counts, including unavailable snapshots."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.dashboard.owned_items import OwnedItemsIndex, normalize_item_name


def item(name, count, location="inventory", **extra):
    return {"DisplayName": name, "Count": count, "Location": location, **extra}


def profile(inventory=None, character_storage=None, account_storage=None):
    return {
        "inventory": inventory or [],
        "character_storage": character_storage or [],
        "account_storage": account_storage or [],
    }


class OwnedItemTests(unittest.TestCase):
    def test_duplicate_stacks_sum_and_warehouse_combines_both_locations(self):
        data = profile(
            [item("나무 진액", 12), item("나무 진액", 8)],
            [item("나무 진액", 30, "character_storage")],
            [item("나무 진액", 40, "account_storage"), item("나무 진액", 40, "account_storage")],
        )
        counts = OwnedItemsIndex.from_profile(data).for_name("나무 진액")
        self.assertEqual((counts.inventory, counts.character_storage, counts.account_storage), (20, 30, 80))
        self.assertEqual((counts.warehouse, counts.total, counts.complete), (110, 130, True))

    def test_empty_valid_locations_are_known_zero(self):
        counts = OwnedItemsIndex.from_profile(profile()).for_name("황금 양털")
        self.assertEqual((counts.inventory, counts.warehouse, counts.total), (0, 0, 0))
        self.assertTrue(counts.complete)

    def test_missing_snapshot_is_unknown_not_zero(self):
        for source in (None, {}, [], "failed"):
            with self.subTest(source=source):
                counts = OwnedItemsIndex.from_profile(source).for_name("황금 양털")
                self.assertEqual((counts.inventory, counts.warehouse, counts.total), (None, None, None))
                self.assertFalse(counts.complete)

    def test_missing_location_preserves_other_known_locations_but_not_total(self):
        data = {"inventory": [item("양털", 3)], "account_storage": []}
        counts = OwnedItemsIndex.from_profile(data).for_name("양털")
        self.assertEqual((counts.inventory, counts.character_storage, counts.account_storage), (3, None, 0))
        self.assertIsNone(counts.warehouse)
        self.assertIsNone(counts.total)

    def test_malformed_location_is_not_silently_treated_as_empty(self):
        for rows in (None, {}, "offline", [None], [{"DisplayName": "양털"}], [{"Count": 4}]):
            with self.subTest(rows=rows):
                data = profile()
                data["inventory"] = rows
                counts = OwnedItemsIndex.from_profile(data).for_name("양털")
                self.assertIsNone(counts.inventory)
                self.assertEqual(counts.warehouse, 0)
                self.assertIsNone(counts.total)

    def test_invalid_counts_do_not_create_false_totals(self):
        for count in (-1, True, 1.5, "3", None):
            with self.subTest(count=count):
                data = profile([item("양털", 2), item("양털", count)])
                self.assertIsNone(OwnedItemsIndex.from_profile(data).for_name("양털").total)

    def test_tags_html_entities_and_repeated_whitespace_normalize(self):
        data = profile([item(" <color=#FFD700>나무</color>\t 진액 ", 3), item("나무&nbsp;진액", 2)])
        counts = OwnedItemsIndex.from_profile(data).for_name("나무  진액")
        self.assertEqual(counts.total, 5)
        self.assertEqual(normalize_item_name("<b>옷감+</b>"), "옷감+")

    def test_exact_names_do_not_mix_tiers_prefixes_or_suffixes(self):
        data = profile([item("양털", 2), item("황금 양털", 5), item("황금 양털+", 8), item("제작 스크롤: 양털", 10)])
        index = OwnedItemsIndex.from_profile(data)
        self.assertEqual(index.for_name("양털").total, 2)
        self.assertEqual(index.for_name("황금 양털").total, 5)
        self.assertEqual(index.for_name("황금 양털+").total, 8)

    def test_equipped_and_misplaced_entries_are_excluded(self):
        data = profile([item("신발", 2), item("신발", 1, "equipment"), item("신발", 10, "account_storage")])
        self.assertEqual(OwnedItemsIndex.from_profile(data).for_name("신발").total, 2)

    def test_locked_items_still_count_as_owned(self):
        data = profile([item("양털", 7, IsLocked=True)])
        self.assertEqual(OwnedItemsIndex.from_profile(data).for_name("양털").total, 7)

    def test_old_bucket_without_repeated_location_field_is_supported(self):
        data = profile([{"DisplayName": "양털", "Count": 7}])
        self.assertEqual(OwnedItemsIndex.from_profile(data).for_name("양털").total, 7)

    def test_only_current_profile_is_used_when_rebuilding_for_character_switch(self):
        old = profile([item("양털", 90)], account_storage=[item("양털", 50, "account_storage")])
        current = profile([item("양털", 2)], account_storage=[item("양털", 50, "account_storage")])
        index = OwnedItemsIndex.from_profile(old)
        self.assertEqual(index.for_name("양털").total, 140)
        index = OwnedItemsIndex.from_profile(current)
        self.assertEqual(index.for_name("양털").total, 52)

    def test_source_is_not_mutated_and_later_source_changes_need_new_index(self):
        data = profile([item("양털", 7)])
        before = copy.deepcopy(data)
        index = OwnedItemsIndex.from_profile(data)
        self.assertEqual(data, before)
        data["inventory"][0]["Count"] = 9
        self.assertEqual(index.for_name("양털").total, 7)
        self.assertEqual(OwnedItemsIndex.from_profile(data).for_name("양털").total, 9)

    def test_invalid_lookup_name_is_unknown(self):
        index = OwnedItemsIndex.from_profile(profile())
        for name in (None, 1, "", "<b></b>"):
            with self.subTest(name=name):
                self.assertIsNone(index.for_name(name).total)


if __name__ == "__main__":
    unittest.main()
