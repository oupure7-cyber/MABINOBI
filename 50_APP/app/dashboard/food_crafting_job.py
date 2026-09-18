"""Generic '재료 채집 -> 제작' JOB worker (added 2026-09-18 for 야채볶음10개/야채볶음 50개).

execute_crafting is a single travel+craft+collect call - not the 7-slot altering-queue system
altering_routine.py deals with - so this is a much simpler one-shot worker: top up every
required ingredient to its target total (gathering whatever's short), then craft the requested
count in as few execute_crafting calls as the facility's per-call cap allows, then finish.
There's no internal repeat loop here - re-running the whole thing N times is what the JOB
queue's own `◀ N ▶` stepper is for (see job_queue.py).

Same shape as every other JOB worker in this app (status/blocked/stopped signals,
request_stop()), and the same safeguard: stops immediately - never auto-clicks through - the
moment anything comes back `blocked`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from ..cli_client import run_cli
from .widgets import classify_cli_result

GATHER_TIMEOUT = 900  # a full 100-item execute_gathering call can take several minutes
CRAFT_TIMEOUT = 900  # execute_crafting does travel + N crafts + collection in one call


@dataclass(frozen=True)
class Ingredient:
    name: str
    qty: int  # total needed (inventory + character storage + account storage combined)


class FoodCraftWorker(QThread):
    status = Signal(str)
    blocked = Signal(str)
    stopped = Signal()

    def __init__(self, recipe: str, craft_count: int, ingredients: tuple[Ingredient, ...], parent=None):
        super().__init__(parent)
        self._recipe = recipe
        self._craft_count = craft_count
        self._ingredients = ingredients
        self._stop_requested = False
        self._blocked_stop = False
        self._max_craft_per_call: int | None = None  # learned from a facility's invalid_count reply

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        self.status.emit(f"'{self._recipe}' {self._craft_count}개 제작 준비 - 재료 확인 중...")
        ok = True
        for ing in self._ingredients:
            if self._stop_requested:
                ok = False
                break
            if not self._ensure_ingredient(ing):
                ok = False
                break
        if ok and not self._stop_requested:
            ok = self._craft_all()

        if not self._blocked_stop:
            if ok and not self._stop_requested:
                self.status.emit(f"✅ '{self._recipe}' {self._craft_count}개 제작 완료")
            else:
                self.status.emit("루틴 정지")
        self.stopped.emit()

    # -- ingredients -----------------------------------------------------------

    def _fetch_count(self, name: str) -> int:
        data = run_cli("get_items", json.dumps({"name": name}, ensure_ascii=False), timeout=30)
        return sum(item.get("Count", 0) for item in data if item.get("DisplayName") == name) if isinstance(data, list) else 0

    def _ensure_ingredient(self, ing: Ingredient) -> bool:
        owned = self._fetch_count(ing.name)
        while owned < ing.qty and not self._stop_requested:
            self.status.emit(f"⏳ '{ing.name}' 채집 중... (보유 {owned}/{ing.qty}, 약 2분 소요)")
            body = json.dumps({"displayName": ing.name}, ensure_ascii=False)
            data = run_cli("execute_gathering", body, timeout=GATHER_TIMEOUT)
            ok, reason = classify_cli_result(data)
            if not ok:
                if self._check_blocked(data):
                    return False
                self.status.emit(f"⚠️ '{ing.name}' 채집 실패: {reason}")
                return False
            gained = data.get("gained") if isinstance(data, dict) else None
            self.status.emit(f"⛏️ '{ing.name}' 채집 완료{f' ({gained}개)' if gained else ''}")
            owned = self._fetch_count(ing.name)
        return owned >= ing.qty

    # -- crafting ----------------------------------------------------------------

    def _craft_all(self) -> bool:
        remaining = self._craft_count
        while remaining > 0 and not self._stop_requested:
            chunk = remaining if self._max_craft_per_call is None else min(remaining, self._max_craft_per_call)
            self.status.emit(f"⏳ '{self._recipe}' 제작 중... ({chunk}개, 이동 포함, 최대 15분)")
            body = json.dumps({"displayName": self._recipe, "craftCount": chunk}, ensure_ascii=False)
            data = run_cli("execute_crafting", body, timeout=CRAFT_TIMEOUT)
            ok, reason = classify_cli_result(data)
            if ok:
                self.status.emit(f"🍳 '{self._recipe}' {chunk}개 제작 완료")
                remaining -= chunk
                continue
            if self._check_blocked(data):
                return False
            error = data.get("error") if isinstance(data, dict) else None
            max_count = data.get("maxCount") if isinstance(data, dict) else None
            if error == "invalid_count" and isinstance(max_count, int) and 0 < max_count < chunk:
                # facility caps a single execute_crafting call lower than we asked for - learn
                # the real cap and retry immediately in smaller chunks from here on.
                self._max_craft_per_call = max_count
                continue
            self.status.emit(f"⚠️ '{self._recipe}' 제작 실패: {reason}")
            return False
        return remaining <= 0

    def _check_blocked(self, data) -> bool:
        kind = data.get("kind") if isinstance(data, dict) else None
        if kind:
            self.blocked.emit(str(kind))
            self._stop_requested = True
            self._blocked_stop = True
            return True
        return False
