"""'강철괴 무한' routine: keeps 금속 가공 시설's 7-slot altering queue full forever by
looping collect -> decide -> gather/queue. Recipe chain (user-supplied, 2026-09-18):

    강철괴 x3  <- 철괴 x3 + 석탄 x4                (5min, 금속 가공 시설)
    철괴 x3    <- 광석 x20   ("철괴(광석)" recipe)   (30s,  금속 가공 시설)
    철괴 x3    <- 철 광석 x10 ("철괴(철 광석)" recipe) (30s,  금속 가공 시설)
    광석/철 광석/석탄 <- execute_gathering

Runs in its own QThread since execute_gathering/execute_altering block for real minutes at
a time (see CHANGELOG 2026-09-18's timeout bug) and the whole point is to keep doing that
indefinitely - only ever touches the GUI through signals.

Respects the official safeguards this project's own spec calls for (00_SPEC/03_requirements.md):
stops itself - rather than looping through it - the moment any call comes back `blocked`
(the 1-hour continuous-use confirmation popup, an interrupting dialog, etc.), and always
leaves a way for the user to regain control (the Stop button). It does NOT track a 정령의
날개 daily budget cap yet (00_SPEC calls for one) - every gather/alter call here costs 5,
uncapped, for as long as it runs.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QThread, Signal

from ..cli_client import run_cli
from .widgets import classify_cli_result

FACILITY = "금속 가공 시설"
QUEUE_CAPACITY = 7

STEEL_INGOT = "강철괴"
IRON_INGOT = "철괴"
COAL = "석탄"
ORE = "광석"
IRON_ORE = "철 광석"

TICK_IDLE_SECONDS = 8


class SteelRoutineWorker(QThread):
    status = Signal(str)
    blocked = Signal(str)
    stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = False
        self._blocked_stop = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        self.status.emit("강철괴 무한 루틴 시작")
        while not self._stop_requested:
            try:
                acted = self._tick()
            except Exception as exc:  # noqa: BLE001 - one bad response shouldn't kill the loop
                acted = False
                self.status.emit(f"⚠️ 예외 발생, 계속 진행: {exc}")
            if self._stop_requested:
                break
            if not acted:
                self._sleep_interruptible(TICK_IDLE_SECONDS)
        if not self._blocked_stop:
            self.status.emit("루틴 정지")
        self.stopped.emit()

    def _sleep_interruptible(self, seconds: int) -> None:
        for _ in range(seconds):
            if self._stop_requested:
                return
            self.msleep(1000)

    # -- one cycle: collect what's done, then queue or gather one thing -----

    def _tick(self) -> bool:
        works = run_cli("get_altering_works", timeout=30)
        if not isinstance(works, dict):
            self.status.emit(f"⚠️ 대기열 조회 실패: {works}")
            return False

        facility_works = [w for w in works.get("works", []) if w.get("FacilityName") == FACILITY]
        completed = [w for w in facility_works if w.get("State") == "Completed"]
        active = [w for w in facility_works if w.get("State") in ("NotStarted", "InProgress")]

        acted = False
        if completed:
            if self._collect(completed[0]["DisplayName"]):
                acted = True
            if self._stop_requested:
                return acted

        free_slots = QUEUE_CAPACITY - len(active)
        if free_slots <= 0:
            if not acted:
                self.status.emit(f"대기열 가득 참 ({len(active)}/{QUEUE_CAPACITY})")
            return acted

        inventory = self._inventory_counts()
        iron_ingot, coal, ore, iron_ore = (
            inventory[IRON_INGOT],
            inventory[COAL],
            inventory[ORE],
            inventory[IRON_ORE],
        )

        if iron_ingot >= 3 and coal >= 4:
            return self._queue_altering(STEEL_INGOT, f"강철괴 가공 등록 (철괴 {iron_ingot}, 석탄 {coal} 보유 중)") or acted
        if iron_ore >= 10:
            return self._queue_altering("철괴(철 광석)", f"철괴 가공 등록 - 철 광석 사용 (보유 {iron_ore})") or acted
        if ore >= 20:
            return self._queue_altering("철괴(광석)", f"철괴 가공 등록 - 광석 사용 (보유 {ore})") or acted

        # Not enough of anything to queue - go gather whichever raw material is shortest.
        if iron_ore < 10 and (ore < 20 or iron_ore <= ore):
            return self._gather(IRON_ORE) or acted
        if ore < 20:
            return self._gather(ORE) or acted
        return self._gather(COAL) or acted

    # -- individual CLI actions -------------------------------------------

    def _inventory_counts(self) -> dict[str, int]:
        counts = {}
        for name in (IRON_INGOT, COAL, ORE, IRON_ORE):
            data = run_cli("get_items", json.dumps({"name": name}, ensure_ascii=False), timeout=30)
            counts[name] = (
                sum(item.get("Count", 0) for item in data if item.get("DisplayName") == name)
                if isinstance(data, list)
                else 0
            )
        return counts

    def _collect(self, probe_display_name: str) -> bool:
        body = json.dumps({"displayName": probe_display_name}, ensure_ascii=False)
        data = run_cli("complete_altering_work", body, timeout=120)
        ok, reason = classify_cli_result(data)
        if ok:
            collected = data.get("collected") if isinstance(data, dict) else None
            self.status.emit(f"✅ 회수 완료{f' ({collected})' if collected else ''}")
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ 회수 실패: {reason}")
        return False

    def _queue_altering(self, display_name: str, log_message: str) -> bool:
        body = json.dumps({"displayName": display_name}, ensure_ascii=False)
        data = run_cli("execute_altering", body, timeout=120)
        ok, reason = classify_cli_result(data)
        if ok:
            self.status.emit(f"🔧 {log_message}")
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ 가공 등록 실패({display_name}): {reason}")
        return False

    def _gather(self, item_name: str) -> bool:
        body = json.dumps({"displayName": item_name}, ensure_ascii=False)
        data = run_cli("execute_gathering", body, timeout=900)
        ok, reason = classify_cli_result(data)
        if ok:
            gained = data.get("gained") if isinstance(data, dict) else None
            self.status.emit(f"⛏️ '{item_name}' 채집 완료{f' ({gained}개)' if gained else ''}")
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ '{item_name}' 채집 실패: {reason}")
        return False

    def _check_blocked(self, data) -> bool:
        kind = data.get("kind") if isinstance(data, dict) else None
        if kind:
            self.blocked.emit(str(kind))
            self._stop_requested = True
            self._blocked_stop = True
            return True
        return False
