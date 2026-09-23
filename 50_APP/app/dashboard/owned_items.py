"""Owned quantities from one current character snapshot, without game calls.

``None`` means a location could not be read; an empty but valid list means a
confirmed zero. Account storage is taken once, from this profile alone, so old
snapshots belonging to another character/account never inflate the total.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from html import unescape
import re
import unicodedata


_TAGS = re.compile(r"<[^>]*>")
_LOCATIONS = ("inventory", "character_storage", "account_storage")


def normalize_item_name(name: object) -> str:
    """Keep exact item identities while ignoring markup and repeated whitespace."""
    if not isinstance(name, str):
        return ""
    plain = _TAGS.sub("", unescape(name))
    return " ".join(unicodedata.normalize("NFC", plain).split())


def _sum_known(*amounts: int | None) -> int | None:
    return None if any(amount is None for amount in amounts) else sum(amounts)


@dataclass(frozen=True)
class OwnedItemCounts:
    inventory: int | None = None
    character_storage: int | None = None
    account_storage: int | None = None

    @property
    def warehouse(self) -> int | None:
        return _sum_known(self.character_storage, self.account_storage)

    @property
    def total(self) -> int | None:
        return _sum_known(self.inventory, self.character_storage, self.account_storage)

    @property
    def complete(self) -> bool:
        return self.total is not None


def _location_counts(profile: Mapping, location: str) -> dict[str, int] | None:
    rows = profile.get(location)
    if not isinstance(rows, list):
        return None
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            return None
        # The bucket identifies the location for old snapshots without Location.
        # Explicitly different locations (including equipped items) do not belong.
        if row.get("Location", location) != location:
            continue
        name = normalize_item_name(row.get("DisplayName"))
        count = row.get("Count")
        if not name or type(count) is not int or count < 0:
            # A partial/malformed location must not masquerade as complete stock.
            return None
        counts[name] = counts.get(name, 0) + count
    return counts


@dataclass(frozen=True)
class OwnedItemsIndex:
    _by_location: Mapping[str, dict[str, int] | None]

    @classmethod
    def from_profile(cls, profile: object) -> OwnedItemsIndex:
        """Index a single current profile; missing/invalid locations stay unknown."""
        source = profile if isinstance(profile, Mapping) else {}
        return cls({location: _location_counts(source, location) for location in _LOCATIONS})

    def for_name(self, display_name: object) -> OwnedItemCounts:
        """Return exact-name carried, personal/shared warehouse and total counts."""
        name = normalize_item_name(display_name)
        if not name:
            return OwnedItemCounts()
        values = []
        for location in _LOCATIONS:
            counts = self._by_location.get(location)
            values.append(None if counts is None else counts.get(name, 0))
        return OwnedItemCounts(*values)
