"""Background character-switch detection AND active-character freshness (see
app/character_profiles.py for the actual logic - this is just the QThread/QTimer
plumbing around it).

Every 2s, opportunistically (skipping the tick entirely if the CLI is busy with
something else - see cli_client.try_run_cli) polls both get_currencies and get_items.
currencies feed the switch check; if that fires (or this is the very first poll, which
has nothing to compare against yet), a heavier get_my_info + get_items re-fetch
identifies which saved profile is now active. Otherwise, if this tick's items differ at
all from what's on disk for the already-active profile, the file is refreshed in place -
so the profile a user is currently playing stays current without waiting for a switch.

inventory_updated also reports unchanged successful polls for the live stock display.
Identification and failed reads report None. A skipped (busy) currency/item poll
reports nothing; the last successful display is retained until it becomes stale.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .. import character_profiles
from ..cli_client import run_cli, try_run_cli

POLL_INTERVAL_MS = 2000


def _valid_my_info(my_info: object) -> bool:
    if not isinstance(my_info, dict) or my_info.get("error"):
        return False
    for key in ("EnabledCombatJobDisplayName", "RealmName"):
        if not isinstance(my_info.get(key), str) or not my_info[key].strip():
            return False
    score = my_info.get("CombatScore")
    if isinstance(score, dict):
        score = score.get("Value")
    return type(score) in (int, float) and math.isfinite(score) and score >= 0


def _valid_items(items: object) -> bool:
    if not isinstance(items, list):
        return False
    return all(
        isinstance(item, dict)
        and isinstance(item.get("Location"), str) and bool(item["Location"])
        and isinstance(item.get("DisplayName"), str) and bool(item["DisplayName"].strip())
        and type(item.get("Count")) is int and item["Count"] >= 0
        for item in items
    )


class PollWorker(QThread):
    polled = Signal(object, object)  # raw results: list, failure dict, or skipped None

    def run(self) -> None:
        try:
            currencies = try_run_cli("get_currencies")
            items = try_run_cli("get_items")
        except (OSError, ValueError):
            currencies, items = {"error": "poll_failed"}, {"error": "poll_failed"}
        # Do not collapse a skipped try_run_cli call into the same state as a
        # real failure. Routine work regularly holds the shared CLI lock.
        self.polled.emit(currencies, items)


class CharacterIdentifyWorker(QThread):
    identified = Signal(object, object)  # (my_info or None, items or None)

    def run(self) -> None:
        try:
            my_info = run_cli("get_my_info")
            items = run_cli("get_items")
        except (OSError, ValueError):
            my_info, items = None, None
        self.identified.emit(
            my_info if _valid_my_info(my_info) else None,
            items if _valid_items(items) else None,
        )


class CharacterWatcher(QObject):
    profile_updated = Signal(dict, list)  # (current profile, all profiles)
    inventory_updated = Signal(object)  # fresh current profile, or None if unknown

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self._last_currencies = None
        self._active_profile = None
        self._poll_worker = None
        self._poll_pending = False
        self._identify_worker = None
        self._identifying = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(POLL_INTERVAL_MS)

    def stop(self) -> None:
        self._timer.stop()
        for worker in (self._poll_worker, self._identify_worker):
            if worker is not None and worker.isRunning():
                worker.wait(2000)

    def _tick(self) -> None:
        if self._identifying or (self._identify_worker is not None and self._identify_worker.isRunning()):
            return
        if self._poll_pending or (self._poll_worker is not None and self._poll_worker.isRunning()):
            return
        self._poll_pending = True
        self._poll_worker = PollWorker(self)
        self._poll_worker.polled.connect(self._on_polled)
        self._poll_worker.start()

    def _on_polled(self, currencies: object, items: object) -> None:
        self._poll_pending = False
        if self._identifying or (self._identify_worker is not None and self._identify_worker.isRunning()):
            return
        # A busy CLI gives no currency response, so we cannot establish the
        # character. Preserve the last display unless a read explicitly failed.
        if currencies is None:
            if items is not None and not _valid_items(items):
                self.inventory_updated.emit(None)
            return
        if not isinstance(currencies, list):
            self.inventory_updated.emit(None)
            return
        first_poll = self._last_currencies is None
        switched = character_profiles.detect_switch(self._last_currencies, currencies)
        self._last_currencies = currencies
        if first_poll or switched or self._active_profile is None:
            self._active_profile = None
            self.inventory_updated.emit(None)
            self._identifying = True
            self._identify_worker = CharacterIdentifyWorker(self)
            self._identify_worker.identified.connect(self._on_identified)
            self._identify_worker.start()
            return

        if items is None:
            return
        if not _valid_items(items):
            self.inventory_updated.emit(None)
            return
        if character_profiles.items_changed(self._active_profile, items):
            try:
                profile = character_profiles.refresh_items(
                    self.project_root, self._active_profile["profile_id"], items, self._last_currencies
                )
            except (OSError, ValueError):
                profile = None
            if profile is None:
                self._active_profile = None
                self.inventory_updated.emit(None)
                return
            self._active_profile = profile
            all_profiles = character_profiles.load_profiles(self.project_root)
            self.profile_updated.emit(profile, all_profiles)
        else:
            # Refresh live freshness without rewriting an unchanged file every 2s.
            self._active_profile = dict(
                self._active_profile,
                currencies=currencies,
                last_seen=datetime.now(timezone.utc).astimezone().isoformat(),
            )
        self.inventory_updated.emit(self._active_profile)

    def _on_identified(self, my_info: object, items: object) -> None:
        self._identifying = False
        if not _valid_my_info(my_info) or not _valid_items(items) or not isinstance(self._last_currencies, list):
            self._active_profile = None
            self.inventory_updated.emit(None)
            return
        try:
            profile = character_profiles.match_or_create(self.project_root, my_info, self._last_currencies, items)
        except (OSError, ValueError):
            self._active_profile = None
            self.inventory_updated.emit(None)
            return
        self._active_profile = profile
        all_profiles = character_profiles.load_profiles(self.project_root)
        self.profile_updated.emit(profile, all_profiles)
        self.inventory_updated.emit(profile)
