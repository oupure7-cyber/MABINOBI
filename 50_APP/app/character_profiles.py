"""Per-character data accumulation, keyed by a best-effort identity guess.

The CLI never exposes a character id/name/slot (see 10_RESEARCH) and there is no way
to ask "which character is active right now" - and no assumption is made about how
many characters/servers/accounts a user has (some players keep alts across multiple
servers or even multiple accounts). detect_switch() infers a character switch
indirectly: 냥 토큰/하트 토큰 are character-bound (not account-shared) currencies that a
single character's normal play never changes both of within one 2-second poll tick -
if both change at once between two polls, the active character changed.
match_or_create() then guesses *which* saved profile that new character is (class name
+ same server + close combat score), since there's still no real id to key on. A
profile's `profile_id` (its filename) is an internal key only, stable for matching
purposes - `custom_name`, set via rename_profile() from the 캐릭터 관리 dialog, is what a
user actually sees once they've bothered to name a character.

Between switches, the active character's file is kept current too: every poll tick also
re-fetches get_items and, if it differs at all from what's on disk (items_changed()),
refresh_items() rewrites just the item fields (+ last_seen) - no need to wait for a
switch, or a fresh get_my_info, to know inventory/storage changed (user request,
2026-09-19: "활성 캐릭터 데이터가 스냅샷과 조금이라도 다르면 파일도 최신으로 유지").
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR_NAME = "character_data"

# Some item DisplayNames come with rich-text markup, e.g. "<color=#FFD700>레어</color>
# 반지" - strip the tags for search/display, keep the text they wrap (user request,
# 2026-09-19).
_TAG_RE = re.compile(r"<[^>]*>")


def _clean_name(name: str) -> str:
    return _TAG_RE.sub("", name)

# Character-bound currencies used to infer a character switch (user-identified, 2026-09-19).
WATCHED_CURRENCIES = ("냥 토큰", "하트 토큰")

# Same class, and combat score within this relative tolerance of a saved profile's last
# known value, counts as "probably the same character" rather than a different alt.
COMBAT_SCORE_MATCH_TOLERANCE = 0.10


def data_dir(project_root: Path) -> Path:
    path = Path(project_root) / DATA_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _stat(stats: dict, key: str, default=0):
    """get_my_info's stat fields come as {DisplayName, Value}, not bare numbers."""
    field = stats.get(key, default) if isinstance(stats, dict) else default
    return field.get("Value", default) if isinstance(field, dict) else field


def _amount(currencies: list, name: str) -> float:
    for entry in currencies:
        if isinstance(entry, dict) and entry.get("DisplayName") == name:
            return entry.get("Amount", 0)
    return 0


def detect_switch(prev_currencies: list | None, curr_currencies: list) -> bool:
    """True only if BOTH watched currencies changed since the previous poll.

    prev_currencies is None on the very first poll (nothing to compare against yet) -
    that case is not a "switch", the caller is expected to run the identify flow once
    unconditionally on first poll instead.
    """
    if prev_currencies is None:
        return False
    return all(
        _amount(prev_currencies, name) != _amount(curr_currencies, name)
        for name in WATCHED_CURRENCIES
    )


def load_profiles(project_root: Path) -> list[dict]:
    profiles = []
    for path in sorted(data_dir(project_root).glob("profile_*.json")):
        try:
            profiles.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return profiles


def _profile_path(project_root: Path, profile_id: str) -> Path:
    return data_dir(project_root) / f"{profile_id}.json"


def save_profile(project_root: Path, profile: dict) -> None:
    _profile_path(project_root, profile["profile_id"]).write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _next_profile_id(profiles: list[dict]) -> str:
    used = set()
    for p in profiles:
        try:
            used.add(int(p["profile_id"].removeprefix("profile_")))
        except (KeyError, ValueError):
            continue
    n = 1
    while n in used:
        n += 1
    return f"profile_{n}"


def _split_by_location(items: list) -> dict:
    by_location = {"inventory": [], "character_storage": [], "account_storage": []}
    for item in items if isinstance(items, list) else []:
        loc = item.get("Location") if isinstance(item, dict) else None
        if loc in by_location:
            by_location[loc].append(item)
    return by_location


def _canonical(items: list) -> list:
    """Order-independent content comparison key for a list of item dicts."""
    return sorted(json.dumps(item, sort_keys=True, ensure_ascii=False) for item in items)


def items_changed(profile: dict, items: list) -> bool:
    """True if a fresh get_items result differs at all from what's stored in profile."""
    fresh = _split_by_location(items)
    return any(
        _canonical(profile.get(key, [])) != _canonical(fresh[key])
        for key in ("inventory", "character_storage", "account_storage")
    )


def refresh_items(project_root: Path, profile_id: str, items: list, currencies: list | None = None) -> dict | None:
    """Keep an already-identified active profile's item snapshot (+ last_seen) current
    without a fresh get_my_info call - used every poll tick the active character's
    items differ at all from what's on disk, not just on a detected switch.

    Returns None (a harmless no-op) if profile_id no longer exists - e.g. the user
    deleted it from 캐릭터 관리 while that character was still the active one.
    """
    for profile in load_profiles(project_root):
        if profile["profile_id"] == profile_id:
            profile.update(_split_by_location(items))
            if currencies is not None:
                profile["currencies"] = currencies
            profile["last_seen"] = datetime.now(timezone.utc).astimezone().isoformat()
            save_profile(project_root, profile)
            return profile
    return None


def _find_match(profiles: list[dict], class_name: str, realm_name: str, combat_score: float) -> dict | None:
    best = None
    best_diff = None
    for p in profiles:
        if p.get("class_name") != class_name:
            continue
        # Same class + score on a *different* server/account is a different character -
        # without this, two unrelated alts that happen to look alike could get merged,
        # and their account storage (see below) would then mix across servers/accounts.
        if p.get("stats", {}).get("RealmName") != realm_name:
            continue
        prev_score = _stat(p.get("stats", {}), "CombatScore", 0) or 0
        if prev_score == 0 and combat_score == 0:
            diff = 0.0
        elif prev_score == 0 or combat_score == 0:
            continue
        else:
            diff = abs(combat_score - prev_score) / max(prev_score, combat_score)
        if diff <= COMBAT_SCORE_MATCH_TOLERANCE and (best_diff is None or diff < best_diff):
            best, best_diff = p, diff
    return best


def match_or_create(project_root: Path, my_info: dict, currencies: list, items: list) -> dict:
    """Upsert the profile this snapshot belongs to.

    account_storage is saved *inside* the profile rather than one shared file - it's
    only shared across characters of the same account+server, and a single global file
    would get silently overwritten with the wrong data the moment a different
    server/account's character was detected (there's no way to tell those apart other
    than by tying the snapshot to the profile it was captured alongside).

    Returns the (possibly newly-created) profile dict that was just saved.
    """
    class_name = my_info.get("EnabledCombatJobDisplayName", "") if isinstance(my_info, dict) else ""
    realm_name = my_info.get("RealmName", "") if isinstance(my_info, dict) else ""
    combat_score = (_stat(my_info, "CombatScore", 0) or 0) if isinstance(my_info, dict) else 0

    by_location = _split_by_location(items)

    profiles = load_profiles(project_root)
    existing = _find_match(profiles, class_name, realm_name, combat_score)
    profile = {
        "profile_id": existing["profile_id"] if existing else _next_profile_id(profiles),
        "custom_name": existing.get("custom_name") if existing else None,
        "class_name": class_name,
        "last_seen": datetime.now(timezone.utc).astimezone().isoformat(),
        "stats": my_info if isinstance(my_info, dict) else {},
        "currencies": currencies if isinstance(currencies, list) else [],
        "inventory": by_location["inventory"],
        "character_storage": by_location["character_storage"],
        "account_storage": by_location["account_storage"],
    }
    save_profile(project_root, profile)
    return profile


def rename_profile(project_root: Path, profile_id: str, custom_name: str) -> None:
    """Set the user-chosen display name shown in place of the class name everywhere."""
    for profile in load_profiles(project_root):
        if profile["profile_id"] == profile_id:
            profile["custom_name"] = custom_name.strip() or None
            save_profile(project_root, profile)
            return


def delete_profile(project_root: Path, profile_id: str) -> None:
    """Delete this app's local record only - has no effect on the in-game character."""
    path = _profile_path(project_root, profile_id)
    if path.is_file():
        path.unlink()


def format_last_seen(iso_timestamp: str) -> str:
    try:
        return datetime.fromisoformat(iso_timestamp).strftime("%Y-%m-%d %H-%M")
    except (TypeError, ValueError):
        return "-"


COMBAT_SCORE_EMOJI = "⚔️"  # crossed swords - falls back to the info panel's 🏆 if a platform lacks it

# (internal key, 창고 tab group label) - the per-character locations, in get_items' own
# Location vocabulary. account_storage is handled separately (see search_items) since
# it's shared, not per-character.
PER_CHARACTER_LOCATIONS = (("inventory", "인벤토리"), ("character_storage", "보관함"))
TOTAL_GROUP_LABEL = "전체 합계"
ACCOUNT_STORAGE_LABEL = "공용보관함"


def _who(profile: dict) -> str:
    """The name a user actually recognizes: their chosen name, else the class name."""
    return profile.get("custom_name") or profile.get("class_name", "")


def display_name(profile: dict) -> str:
    combat_score = _stat(profile.get("stats", {}), "CombatScore", 0) or 0
    return f"{_who(profile)}({COMBAT_SCORE_EMOJI}{combat_score:,})"


def _matching(items: list, needle: str) -> list[dict]:
    result = []
    for item in items:
        name = _clean_name(item.get("DisplayName", ""))
        if needle in name.lower():
            result.append({"name": name, "count": item.get("Count", 0)})
    return result


def search_items(profiles: list[dict], query: str) -> list[dict]:
    """Find `query` (case-insensitive substring) across every profile's inventory/
    character_storage/account_storage. 창고 tab search - see storage_search.py.

    An empty/blank query matches everything (every item is a substring match of "") -
    the 창고 tab shows the full known inventory rather than nothing when the search box
    is blank.

    Returns groups in a fixed order:
    1. "전체 합계" - every matching item summed across every character's inventory +
       character_storage + the account storage below (skipped if empty).
    2. "공용보관함" - one single group, not one per character - it's shared by every
       character on that account+server, so repeating it per character was redundant.
       De-duplicated by (name, count) rather than summed: a genuinely different
       server/account's account storage would otherwise get merged into a fabricated
       total that doesn't exist in-game (skipped if empty).
    3. One group per (profile, inventory/character_storage) that has a match, labelled
       "이름/서버 - 위치" and sorted by that label.
    """
    needle = query.strip().lower()

    character_groups = []
    for profile in profiles:
        who = _who(profile)
        realm = profile.get("stats", {}).get("RealmName", "")
        for key, location_label in PER_CHARACTER_LOCATIONS:
            matches = sorted(_matching(profile.get(key, []), needle), key=lambda entry: entry["name"])
            if matches:
                character_groups.append({"label": f"{who}/{realm} - {location_label}", "items": matches})
    character_groups.sort(key=lambda g: g["label"])

    seen = set()
    account_items = []
    for profile in profiles:
        for entry in _matching(profile.get("account_storage", []), needle):
            key = (entry["name"], entry["count"])
            if key not in seen:
                seen.add(key)
                account_items.append(entry)
    account_items.sort(key=lambda entry: entry["name"])
    account_group = [{"label": ACCOUNT_STORAGE_LABEL, "items": account_items}] if account_items else []

    totals: dict[str, int] = {}
    for group in character_groups:
        for entry in group["items"]:
            totals[entry["name"]] = totals.get(entry["name"], 0) + entry["count"]
    for entry in account_items:
        totals[entry["name"]] = totals.get(entry["name"], 0) + entry["count"]
    total_items = sorted(
        ({"name": name, "count": count} for name, count in totals.items()), key=lambda entry: entry["name"]
    )
    total_group = [{"label": TOTAL_GROUP_LABEL, "items": total_items}] if total_items else []

    return total_group + account_group + character_groups
