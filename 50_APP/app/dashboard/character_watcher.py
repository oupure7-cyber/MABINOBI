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
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from .. import character_profiles
from ..cli_client import run_cli, try_run_cli

POLL_INTERVAL_MS = 2000


class PollWorker(QThread):
    polled = Signal(object, object)  # (currencies or None, items or None)

    def run(self) -> None:
        currencies = try_run_cli("get_currencies")
        items = try_run_cli("get_items")
        self.polled.emit(
            currencies if isinstance(currencies, list) else None,
            items if isinstance(items, list) else None,
        )


class CharacterIdentifyWorker(QThread):
    identified = Signal(dict, list)  # (my_info, items)

    def run(self) -> None:
        my_info = run_cli("get_my_info")
        items = run_cli("get_items")
        self.identified.emit(
            my_info if isinstance(my_info, dict) else {},
            items if isinstance(items, list) else [],
        )


class CharacterWatcher(QObject):
    profile_updated = Signal(dict, list)  # (current profile, all profiles)

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self._last_currencies = None
        self._active_profile = None
        self._poll_worker = None
        self._identify_worker = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(POLL_INTERVAL_MS)

    def stop(self) -> None:
        self._timer.stop()
        for worker in (self._poll_worker, self._identify_worker):
            if worker is not None and worker.isRunning():
                worker.wait(2000)

    def _tick(self) -> None:
        if self._poll_worker is not None and self._poll_worker.isRunning():
            return
        self._poll_worker = PollWorker(self)
        self._poll_worker.polled.connect(self._on_polled)
        self._poll_worker.start()

    def _on_polled(self, currencies: list | None, items: list | None) -> None:
        switching = False
        if currencies is not None:
            first_poll = self._last_currencies is None
            switched = character_profiles.detect_switch(self._last_currencies, currencies)
            self._last_currencies = currencies
            if (first_poll or switched) and (self._identify_worker is None or not self._identify_worker.isRunning()):
                switching = True
                self._identify_worker = CharacterIdentifyWorker(self)
                self._identify_worker.identified.connect(self._on_identified)
                self._identify_worker.start()

        if not switching and items is not None and self._active_profile is not None:
            if character_profiles.items_changed(self._active_profile, items):
                profile = character_profiles.refresh_items(
                    self.project_root, self._active_profile["profile_id"], items, self._last_currencies
                )
                if profile is not None:
                    self._active_profile = profile
                    all_profiles = character_profiles.load_profiles(self.project_root)
                    self.profile_updated.emit(profile, all_profiles)

    def _on_identified(self, my_info: dict, items: list) -> None:
        profile = character_profiles.match_or_create(self.project_root, my_info, self._last_currencies, items)
        self._active_profile = profile
        all_profiles = character_profiles.load_profiles(self.project_root)
        self.profile_updated.emit(profile, all_profiles)
