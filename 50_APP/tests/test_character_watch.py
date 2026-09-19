"""Run: python -m unittest discover -s tests (no game CLI calls)."""
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import character_profiles as cp
from app import cli_client


def currencies(**amounts):
    return [{"DisplayName": name, "Amount": amount} for name, amount in amounts.items()]


def my_info(class_name, combat_score, realm="칼릭스"):
    # Real get_my_info wraps every stat as {DisplayName, Value}, not a bare number.
    return {
        "EnabledCombatJobDisplayName": class_name,
        "RealmName": realm,
        "CombatScore": {"DisplayName": "전투력", "Value": combat_score},
    }


class DetectSwitchTests(unittest.TestCase):
    def test_first_poll_is_never_a_switch(self):
        self.assertFalse(cp.detect_switch(None, currencies(**{"냥 토큰": 5, "하트 토큰": 3})))

    def test_both_watched_currencies_changing_is_a_switch(self):
        prev = currencies(**{"냥 토큰": 5, "하트 토큰": 3, "골드": 100})
        curr = currencies(**{"냥 토큰": 9, "하트 토큰": 1, "골드": 100})
        self.assertTrue(cp.detect_switch(prev, curr))

    def test_only_one_watched_currency_changing_is_not_a_switch(self):
        prev = currencies(**{"냥 토큰": 5, "하트 토큰": 3})
        curr = currencies(**{"냥 토큰": 9, "하트 토큰": 3})
        self.assertFalse(cp.detect_switch(prev, curr))

    def test_unrelated_currency_changing_is_not_a_switch(self):
        prev = currencies(**{"냥 토큰": 5, "하트 토큰": 3, "골드": 100})
        curr = currencies(**{"냥 토큰": 5, "하트 토큰": 3, "골드": 999})
        self.assertFalse(cp.detect_switch(prev, curr))

    def test_missing_currency_defaults_to_zero(self):
        prev = currencies(**{"골드": 100})  # neither watched currency present yet
        curr = currencies(**{"냥 토큰": 1, "하트 토큰": 1, "골드": 100})
        self.assertTrue(cp.detect_switch(prev, curr))


class MatchOrCreateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def items(self):
        return [
            {"DisplayName": "감자", "Count": 10, "Location": "inventory"},
            {"DisplayName": "양파", "Count": 5, "Location": "character_storage"},
            {"DisplayName": "정령의 날개 충전권", "Count": 1, "Location": "account_storage"},
        ]

    def test_new_character_creates_a_new_profile_file(self):
        profile = cp.match_or_create(self.root, my_info("대검전사", 10000), currencies(**{"냥 토큰": 1, "하트 토큰": 1}), self.items())
        self.assertEqual(profile["profile_id"], "profile_1")
        self.assertEqual(len(cp.load_profiles(self.root)), 1)
        self.assertEqual(profile["inventory"], [self.items()[0]])
        self.assertEqual(profile["character_storage"], [self.items()[1]])
        self.assertEqual(profile["account_storage"], [self.items()[2]])

    def test_account_storage_is_embedded_in_the_profile_not_a_shared_file(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items())
        self.assertFalse((cp.data_dir(self.root) / "account_storage.json").exists())
        [saved] = cp.load_profiles(self.root)
        self.assertEqual(saved["account_storage"], [self.items()[2]])

    def test_same_class_and_score_but_different_realm_creates_a_second_profile(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000, realm="칼릭스"), [], [])
        second = cp.match_or_create(self.root, my_info("대검전사", 10000, realm="루엘라"), [], [])
        self.assertEqual(second["profile_id"], "profile_2")
        self.assertEqual(len(cp.load_profiles(self.root)), 2)

    def test_same_class_close_combat_score_updates_existing_profile(self):
        first = cp.match_or_create(self.root, my_info("대검전사", 10000), [], [])
        second = cp.match_or_create(self.root, my_info("대검전사", 10400), [], [])
        self.assertEqual(first["profile_id"], second["profile_id"])
        self.assertEqual(len(cp.load_profiles(self.root)), 1)

    def test_different_class_creates_a_second_profile(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000), [], [])
        second = cp.match_or_create(self.root, my_info("힐러", 3000), [], [])
        self.assertEqual(second["profile_id"], "profile_2")
        self.assertEqual(len(cp.load_profiles(self.root)), 2)

    def test_same_class_far_apart_combat_score_creates_a_second_profile(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000), [], [])
        second = cp.match_or_create(self.root, my_info("대검전사", 500), [], [])
        self.assertEqual(second["profile_id"], "profile_2")

    def test_renamed_profile_keeps_its_custom_name_across_later_updates(self):
        first = cp.match_or_create(self.root, my_info("대검전사", 10000), [], [])
        cp.rename_profile(self.root, first["profile_id"], "본캐")
        updated = cp.match_or_create(self.root, my_info("대검전사", 10400), [], [])
        self.assertEqual(updated["custom_name"], "본캐")


class ItemsChangedAndRefreshTests(unittest.TestCase):
    """Covers keeping the *active* character's file current between switches -
    user request 2026-09-19: "활성 캐릭터 데이터가 스냅샷과 조금이라도 다르면 파일도 최신으로 유지"."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def items(self, potato_count=10):
        return [
            {"DisplayName": "감자", "Count": potato_count, "Location": "inventory"},
            {"DisplayName": "양파", "Count": 5, "Location": "character_storage"},
        ]

    def test_identical_items_are_not_flagged_as_changed(self):
        profile = cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items())
        self.assertFalse(cp.items_changed(profile, self.items()))

    def test_reordered_but_identical_items_are_not_flagged_as_changed(self):
        profile = cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items())
        self.assertFalse(cp.items_changed(profile, list(reversed(self.items()))))

    def test_a_single_count_change_is_flagged(self):
        profile = cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items(potato_count=10))
        self.assertTrue(cp.items_changed(profile, self.items(potato_count=11)))

    def test_refresh_items_updates_items_and_last_seen_without_touching_stats(self):
        profile = cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items(potato_count=10))
        original_last_seen = profile["last_seen"]
        updated = cp.refresh_items(self.root, profile["profile_id"], self.items(potato_count=99), currencies(**{"골드": 5}))
        self.assertEqual(updated["inventory"][0]["Count"], 99)
        self.assertEqual(updated["currencies"], currencies(**{"골드": 5}))
        self.assertNotEqual(updated["last_seen"], original_last_seen)
        self.assertEqual(updated["class_name"], "대검전사")  # untouched - no get_my_info call needed

    def test_refresh_items_of_a_deleted_profile_is_a_harmless_no_op(self):
        self.assertIsNone(cp.refresh_items(self.root, "profile_99", self.items()))


class SearchItemsTests(unittest.TestCase):
    """창고 tab search - user request 2026-09-19."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def items(self):
        return [
            {"DisplayName": "체력 포션", "Count": 3, "Location": "inventory"},
            {"DisplayName": "강화 체력 포션", "Count": 1, "Location": "character_storage"},
            {"DisplayName": "정령의 날개 충전권", "Count": 2, "Location": "account_storage"},
        ]

    def test_empty_query_returns_everything(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items())
        profiles = cp.load_profiles(self.root)
        for query in ("", "   "):
            groups = cp.search_items(profiles, query)
            labels = [g["label"] for g in groups]
            # 전체 합계 + 공용보관함 + 2 per-character location groups
            self.assertEqual(labels, [
                "전체 합계", "공용보관함", "대검전사/칼릭스 - 보관함", "대검전사/칼릭스 - 인벤토리",
            ])
            self.assertEqual(len(groups[0]["items"]), 3)  # every distinct item, once

    def test_no_profiles_and_empty_query_returns_nothing(self):
        self.assertEqual(cp.search_items([], ""), [])

    def test_no_match_returns_nothing(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items())
        profiles = cp.load_profiles(self.root)
        self.assertEqual(cp.search_items(profiles, "존재하지않는아이템"), [])

    def test_matches_group_by_profile_and_location_with_class_name_when_unnamed(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000, realm="칼릭스"), [], self.items())
        profiles = cp.load_profiles(self.root)
        groups = cp.search_items(profiles, "포션")
        labels = [g["label"] for g in groups]
        self.assertEqual(labels, [
            "전체 합계",
            "대검전사/칼릭스 - 보관함",
            "대검전사/칼릭스 - 인벤토리",
        ])
        inventory_group = next(g for g in groups if g["label"].endswith("인벤토리"))
        self.assertEqual(inventory_group["items"], [{"name": "체력 포션", "count": 3}])

    def test_rich_text_color_tags_are_stripped_but_their_text_is_kept(self):
        items = [{"DisplayName": "<color=#FFD700>레어</color> 반지", "Count": 1, "Location": "inventory"}]
        cp.match_or_create(self.root, my_info("대검전사", 10000), [], items)
        profiles = cp.load_profiles(self.root)
        groups = cp.search_items(profiles, "레어")
        inventory_group = next(g for g in groups if g["label"].endswith("인벤토리"))
        self.assertEqual(inventory_group["items"], [{"name": "레어 반지", "count": 1}])

    def test_matches_use_custom_name_once_renamed(self):
        profile = cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items())
        cp.rename_profile(self.root, profile["profile_id"], "본캐")
        profiles = cp.load_profiles(self.root)
        groups = cp.search_items(profiles, "포션")
        per_character = [g for g in groups if "/" in g["label"]]
        self.assertEqual(len(per_character), 2)
        self.assertTrue(all(g["label"].startswith("본캐/") for g in per_character))

    def test_account_storage_is_a_single_group_named_공용보관함(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000), [], self.items())
        profiles = cp.load_profiles(self.root)
        groups = cp.search_items(profiles, "충전권")
        labels = [g["label"] for g in groups]
        self.assertEqual(labels, ["전체 합계", "공용보관함"])  # no character/server prefix
        account_group = next(g for g in groups if g["label"] == "공용보관함")
        self.assertEqual(account_group["items"], [{"name": "정령의 날개 충전권", "count": 2}])

    def test_account_storage_shared_by_two_characters_is_not_duplicated(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000, realm="칼릭스"), [], self.items())
        cp.match_or_create(self.root, my_info("힐러", 3000, realm="칼릭스"), [], self.items())
        profiles = cp.load_profiles(self.root)
        [account_group] = [g for g in cp.search_items(profiles, "충전권") if g["label"] == "공용보관함"]
        self.assertEqual(account_group["items"], [{"name": "정령의 날개 충전권", "count": 2}])

    def test_total_group_sums_the_same_item_across_characters_and_account_storage(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000, realm="칼릭스"), [], self.items())
        cp.match_or_create(self.root, my_info("힐러", 3000, realm="칼릭스"), [], self.items())
        profiles = cp.load_profiles(self.root)
        [total_group] = [g for g in cp.search_items(profiles, "포션") if g["label"] == "전체 합계"]
        totals = {e["name"]: e["count"] for e in total_group["items"]}
        self.assertEqual(totals, {"체력 포션": 6, "강화 체력 포션": 2})  # 2 characters x each

    def test_searches_across_multiple_profiles(self):
        cp.match_or_create(self.root, my_info("대검전사", 10000, realm="칼릭스"), [], self.items())
        cp.match_or_create(self.root, my_info("힐러", 3000, realm="칼릭스"), [], self.items())
        profiles = cp.load_profiles(self.root)
        groups = cp.search_items(profiles, "포션")
        per_character = [g for g in groups if "/" in g["label"]]
        self.assertEqual(len({g["label"].split("/")[0] for g in per_character}), 2)


class RenameAndDeleteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rename_sets_custom_name(self):
        profile = cp.match_or_create(self.root, my_info("대검전사", 10000), [], [])
        cp.rename_profile(self.root, profile["profile_id"], "본캐")
        [reloaded] = cp.load_profiles(self.root)
        self.assertEqual(reloaded["custom_name"], "본캐")

    def test_rename_with_blank_text_clears_the_custom_name(self):
        profile = cp.match_or_create(self.root, my_info("대검전사", 10000), [], [])
        cp.rename_profile(self.root, profile["profile_id"], "본캐")
        cp.rename_profile(self.root, profile["profile_id"], "   ")
        [reloaded] = cp.load_profiles(self.root)
        self.assertIsNone(reloaded["custom_name"])

    def test_delete_removes_the_profile_file_only(self):
        a = cp.match_or_create(self.root, my_info("대검전사", 10000), [], [])
        b = cp.match_or_create(self.root, my_info("힐러", 3000), [], [])
        cp.delete_profile(self.root, a["profile_id"])
        remaining = cp.load_profiles(self.root)
        self.assertEqual([p["profile_id"] for p in remaining], [b["profile_id"]])

    def test_delete_of_unknown_id_is_a_harmless_no_op(self):
        cp.delete_profile(self.root, "profile_99")  # must not raise


class FormatLastSeenTests(unittest.TestCase):
    def test_formats_as_yyyy_mm_dd_hh_mm(self):
        self.assertEqual(cp.format_last_seen("2026-09-19T21:42:36.863442+09:00"), "2026-09-19 21-42")

    def test_invalid_input_falls_back_to_a_dash(self):
        self.assertEqual(cp.format_last_seen(""), "-")
        self.assertEqual(cp.format_last_seen(None), "-")


class DisplayNameTests(unittest.TestCase):
    def test_always_shows_combat_score_with_emoji_even_without_duplicates(self):
        profile = {"profile_id": "profile_1", "class_name": "대검전사", "stats": my_info("대검전사", 10000)}
        self.assertEqual(cp.display_name(profile), f"대검전사({cp.COMBAT_SCORE_EMOJI}10,000)")

    def test_two_profiles_with_the_same_class_still_show_their_own_score(self):
        a = {"profile_id": "profile_1", "class_name": "대검전사", "stats": my_info("대검전사", 10000)}
        b = {"profile_id": "profile_2", "class_name": "대검전사", "stats": my_info("대검전사", 7500)}
        self.assertEqual(cp.display_name(a), f"대검전사({cp.COMBAT_SCORE_EMOJI}10,000)")
        self.assertEqual(cp.display_name(b), f"대검전사({cp.COMBAT_SCORE_EMOJI}7,500)")

    def test_custom_name_replaces_class_name_when_set(self):
        profile = {"profile_id": "profile_1", "class_name": "대검전사", "custom_name": "본캐", "stats": my_info("대검전사", 10000)}
        self.assertEqual(cp.display_name(profile), f"본캐({cp.COMBAT_SCORE_EMOJI}10,000)")


class TryRunCliTests(unittest.TestCase):
    def test_busy_lock_skips_the_call_entirely(self):
        with cli_client._CLI_LOCK:
            with patch("app.cli_client.subprocess.run") as mock_run:
                result = cli_client.try_run_cli("get_currencies")
        self.assertIsNone(result)
        mock_run.assert_not_called()

    def test_free_lock_calls_through_like_run_cli(self):
        class FakeResult:
            stdout = '{"ok": true}'
            stderr = ""

        with patch("app.cli_client.subprocess.run", return_value=FakeResult()) as mock_run:
            result = cli_client.try_run_cli("get_currencies")
        self.assertEqual(result, {"ok": True})
        mock_run.assert_called_once()

    def test_lock_is_released_after_a_call_so_the_next_one_can_proceed(self):
        class FakeResult:
            stdout = '{"ok": true}'
            stderr = ""

        with patch("app.cli_client.subprocess.run", return_value=FakeResult()):
            cli_client.try_run_cli("get_currencies")
        self.assertTrue(cli_client._CLI_LOCK.acquire(blocking=False))
        cli_client._CLI_LOCK.release()


class CliPathPriorityTests(unittest.TestCase):
    """cli_path()'s priority order - user request 2026-09-19 (not everyone installs to
    the Nexon default folder, see app/dashboard/cli_setup.py)."""

    def setUp(self):
        self._original_custom = cli_client._custom_cli_path
        self._env_patcher = patch.dict("os.environ", {}, clear=False)
        self._env_patcher.start()
        os.environ.pop("MABINOGI_CLI_PATH", None)

    def tearDown(self):
        cli_client._custom_cli_path = self._original_custom
        self._env_patcher.stop()

    def test_defaults_when_nothing_is_configured(self):
        cli_client.set_cli_path(None)
        self.assertEqual(cli_client.cli_path(), cli_client.DEFAULT_CLI_PATH)

    def test_custom_path_overrides_the_default(self):
        cli_client.set_cli_path(r"D:\Games\Mabinogi\MabinogiMobile_CLI.exe")
        self.assertEqual(cli_client.cli_path(), r"D:\Games\Mabinogi\MabinogiMobile_CLI.exe")

    def test_env_var_overrides_both_default_and_custom_path(self):
        cli_client.set_cli_path(r"D:\Games\Mabinogi\MabinogiMobile_CLI.exe")
        os.environ["MABINOGI_CLI_PATH"] = r"E:\Dev\fake_cli.exe"
        self.assertEqual(cli_client.cli_path(), r"E:\Dev\fake_cli.exe")


if __name__ == "__main__":
    unittest.main()
