"""Generalized '가공 무한' routine: keeps every configured altering facility's 7-slot queue
full forever, across four material families (금속/목재/가죽/옷감), following one worker's
round-robin loop (user-specified, 2026-09-18). One CLI-calling worker only, sweeping all four
facilities every round and gathering whatever raw material is most needed in between - not
four separate workers "in parallel". Running multiple workers that hit the same
MabinogiMobile_CLI.exe process at once causes conflicts (see CHANGELOG 2026-09-18, "대화 콘솔
제거" entry). For the same reason, the standalone dashboard window (`routine_dashboard.py`)
never polls the CLI itself - it only listens to this worker's `snapshot` signal.

Full N-tier redesign (user-specified, 2026-09-20; replaces the earlier version that only ever
made it to the 2nd tier - 강철괴/목재+/옷감+/가죽+ - and stopped there). Each family is really a
chain of up to 7 tiers (원재료 → 1차 가공물 → ... → 특급), all sourced from
`10_RESEARCH/05_altering_full_recipe_chains_2026-09-20.md`. Every altering work, at every tier,
produces exactly 3 of its output. From the 3rd tier on, all four families share one shape:

    결과물[n] <- 결과물[n-1] x N + 그 등급 전용 원재료 x M + 계열 공통 보조재료(석탄/나무
                 진액/타닌 가루/양털) x K

with N/M/K progressing 3→4→5→5→5, 15→20→20→20→20, 8→12→16→20→20 identically across metal/
wood/leather/cloth (금속만 맨 앞에 원재료 루트가 2개인 "철괴" 단계가 하나 더 있어 tier 번호가
하나씩 밀려 있을 뿐, 진행 자체는 같다). See `FAMILIES` below for the exact per-tier data.

**목표 등급은 이제 고정이 아니라 런타임 슬라이더로 정한다** (`routine_dashboard.py`의
`TierTargetControl`, 사용자가 각 계열마다 원하는 최종 등급을 드래그로 지정). 슬롯 하나를 채울
때마다 `_plan_one_slot()`이 그 계열의 현재 목표 등급(target_idx)부터 0단계까지 내려가며 "지금
바로 만들 수 있는 가장 높은 단계"를 찾는다. target_idx 미만의 모든 단계는 "그 단계 산출물이
다음 단계 한 바퀴(대기열 7칸) 분 + 5개를 넘어설 때만 초과분을 상위 합성에 쓴다"는 예약 규칙이
걸려 있고, target_idx 자신은 예약 없이 무제한으로 쌓인다 - 이게 사용자가 원한 "필수 개수를
훨씬 초과하면 나머지는 전부 상위 재료로 승격" 동작이다. 위에서 아래로 훑는 순서 자체가 "가능한
한 가장 높은 단계부터" 우선순위를 보장하고, 막히면 자연히 한 단계씩 아래로 폴백한다.

**이번 버전이 자동 채집하는 원재료는 예전과 동일한 범위로 한정된다**: 0단계 원재료
(광석/철 광석/통나무/양털)와 1단계가 쓰는 계열 공통 보조재료(석탄/나무 진액/양털 - 타닌
가루는 예전부터 채집 불가로 확인됨) 뿐이다. 3단계 이상에서 새로 등장하는 전용 원재료(동
광석/백동 광석/은 광석/운철 광석/백금강석, 상급~특급 통나무/생가죽/양털+)와 그 단계들이 추가로
소비하는 보조재료는 이번 버전에서 자동 채집 대상에 넣지 않는다(사용자 지정, 1차 버전) - 보유분만
소비하고, 부족하면 그 단계는 조용히 건너뛰고 한 단계 아래로 폴백한다. 나중에
`get_gatherable_items`로 실측하면 확장할 수 있다.

Scheduling algorithm (round 1: sweep+fill, round 2: gather) is otherwise unchanged from the
2026-09-18 design:

  1. 시설을 한 바퀴 돌 때는 시설 A를 회수하고 바로 A를 끝까지 채운 다음 시설 B로 넘어간다.
  2. 채집은 한 번에 최대 100개까지. 완료된 시설이 4곳 중 3곳 이상이면 회수+재충전 라운드를
     먼저 하고 나서 다음 채집으로 넘어간다.
  3. 원자재 자체를 "언제 채집할지"는 7작업분(`RAW_MATERIAL_BUFFER_MULTIPLIER`배, 기본 5배)에
     못 미치면 그 재료가 채집 후보에 오르는 방식 - 여러 재료 중 목표치 대비 가장 많이 모자란
     것부터, 목표치에 도달할 때까지 계속.

대기열 슬롯 계산: `get_altering_works`의 "Completed"(완료했지만 아직 회수 안 한) 항목도 7칸 중
하나를 그대로 차지한다.

Runs in its own QThread since execute_gathering/execute_altering block for real minutes at a
time - only ever touches the GUI through signals. Stops itself - rather than looping through
it - the moment any call comes back `blocked`, consistent with 00_SPEC/03_requirements.md's
safeguard requirement. Does not track a 정령의 날개 daily budget cap yet (00_SPEC calls for
one) - every gather/alter call costs 5, uncapped.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from ..cli_client import run_cli
from .widgets import classify_cli_result

QUEUE_CAPACITY = 7
# A tier below the current target keeps at least (다음 단계 1회 가공에 필요한 개수 N) x
# QUEUE_CAPACITY of its own stock in reserve; only the amount above that + this margin is
# free to be spent promoting it into the next tier (user-specified, 2026-09-20).
PROMOTION_MARGIN = 5

TICK_IDLE_SECONDS = 8
READY_FACILITY_THRESHOLD = 3  # out of 4 - see scheduling rule 2 in the module docstring
# How many 7-work batches worth of each gatherable raw material to stockpile before a gather
# trip for it is no longer "worth it" (2026-09-18, user request, raised from 2x to 5x after
# noticing the character sat idle a lot between gather trips).
RAW_MATERIAL_BUFFER_MULTIPLIER = 5
# 철 광석/광석 채집 지점은 유독 왕복이 오래 걸린다는 사용자 피드백(2026-09-18) - 이 둘을 캐러
# 갈 때는 목표치 도달 여부와 무관하게 그 자리에서 두 번 연달아 채집(최대 200개)해서 이동
# 시간을 낭비하지 않는다. 다른 재료는 이동이 짧아 그대로 1회.
LONG_TRAVEL_GATHER_REPEAT: dict[str, int] = {"철 광석": 2, "광석": 2}


@dataclass(frozen=True)
class Ingredient:
    """One input consumed by one work of a recipe."""

    material: str
    qty: int
    is_previous_tier: bool  # True: `material` is this family's tier[idx-1].name (a made item)
    gatherable: bool = False  # only meaningful when is_previous_tier=False - see module docstring


@dataclass(frozen=True)
class RecipeOption:
    display_name: str  # exact name to pass to execute_altering
    inputs: tuple[Ingredient, ...]


@dataclass(frozen=True)
class Tier:
    name: str  # output display name, e.g. "강철괴" - also what the target slider labels show
    recipes: tuple[RecipeOption, ...]  # usually 1; tier 0 metal has 2 (광석 route / 철 광석 route)


@dataclass(frozen=True)
class Family:
    key: str
    label: str  # "금속"/"목재"/"가죽"/"옷감"
    facility: str
    tiers: tuple[Tier, ...]  # index 0 = 1차 가공물 ... index len-1 = 특급
    default_target_idx: int = 1  # matches the old hardcoded behavior (강철괴류) until moved
    skip_below: tuple[str, int] | None = None  # (material, min_total) - skip whole family if under

    def raw_material_demand(self) -> dict[str, int]:
        """Gatherable raw materials this family needs, summed per one round of 7 works -
        unchanged in scope from before this redesign (see module docstring)."""
        demand: dict[str, int] = {}
        for tier in self.tiers:
            for option in tier.recipes:
                for ing in option.inputs:
                    if not ing.is_previous_tier and ing.gatherable:
                        demand[ing.material] = demand.get(ing.material, 0) + ing.qty
        return demand


FAMILIES: tuple[Family, ...] = (
    Family(
        key="metal",
        label="금속",
        facility="금속 가공 시설",
        tiers=(
            Tier("철괴", (
                RecipeOption("철괴(철 광석)", (Ingredient("철 광석", 10, False, gatherable=True),)),
                RecipeOption("철괴(광석)", (Ingredient("광석", 20, False, gatherable=True),)),
            )),
            Tier("강철괴", (RecipeOption("강철괴", (
                Ingredient("철괴", 3, True),
                Ingredient("석탄", 4, False, gatherable=True),
            )),)),
            Tier("합금강괴", (RecipeOption("합금강괴", (
                Ingredient("강철괴", 3, True),
                Ingredient("동 광석", 15, False),
                Ingredient("석탄", 8, False),
            )),)),
            Tier("특수강괴", (RecipeOption("특수강괴", (
                Ingredient("합금강괴", 4, True),
                Ingredient("백동 광석", 20, False),
                Ingredient("석탄", 12, False),
            )),)),
            Tier("은합금괴", (RecipeOption("은합금괴", (
                Ingredient("특수강괴", 5, True),
                Ingredient("은 광석", 20, False),
                Ingredient("석탄", 16, False),
            )),)),
            Tier("운철괴", (RecipeOption("운철괴", (
                Ingredient("은합금괴", 5, True),
                Ingredient("운철 광석", 20, False),
                Ingredient("석탄", 20, False),
            )),)),
            Tier("백금강괴", (RecipeOption("백금강괴", (
                Ingredient("운철괴", 5, True),
                Ingredient("백금강석", 20, False),
                Ingredient("석탄", 20, False),
            )),)),
        ),
    ),
    Family(
        key="wood",
        label="목재",
        facility="목재 가공 시설",
        tiers=(
            Tier("목재", (RecipeOption("목재", (Ingredient("통나무", 10, False, gatherable=True),)),)),
            Tier("목재+", (RecipeOption("목재+", (
                Ingredient("목재", 3, True),
                Ingredient("나무 진액", 4, False, gatherable=True),
            )),)),
            Tier("상급 목재", (RecipeOption("상급 목재", (
                Ingredient("목재+", 3, True),
                Ingredient("상급 통나무", 15, False),
                Ingredient("나무 진액", 8, False),
            )),)),
            Tier("상급 목재+", (RecipeOption("상급 목재+", (
                Ingredient("상급 목재", 4, True),
                Ingredient("상급 통나무+", 20, False),
                Ingredient("나무 진액", 12, False),
            )),)),
            Tier("최상급 목재", (RecipeOption("최상급 목재", (
                Ingredient("상급 목재+", 5, True),
                Ingredient("최상급 통나무", 20, False),
                Ingredient("나무 진액", 16, False),
            )),)),
            Tier("최상급 목재+", (RecipeOption("최상급 목재+", (
                Ingredient("최상급 목재", 5, True),
                Ingredient("최상급 통나무+", 20, False),
                Ingredient("나무 진액", 20, False),
            )),)),
            Tier("특급 목재", (RecipeOption("특급 목재", (
                Ingredient("최상급 목재+", 5, True),
                Ingredient("특급 통나무", 20, False),
                Ingredient("나무 진액", 20, False),
            )),)),
        ),
    ),
    Family(
        key="leather",
        label="가죽",
        facility="가죽 가공 시설",
        skip_below=("생가죽", 10),
        tiers=(
            Tier("가죽", (RecipeOption("가죽", (Ingredient("생가죽", 10, False, gatherable=False),)),)),
            Tier("가죽+", (RecipeOption("가죽+", (
                Ingredient("가죽", 3, True),
                Ingredient("타닌 가루", 4, False, gatherable=False),
            )),)),
            Tier("상급 가죽", (RecipeOption("상급 가죽", (
                Ingredient("가죽+", 3, True),
                Ingredient("상급 생가죽", 15, False),
                Ingredient("타닌 가루", 8, False),
            )),)),
            Tier("상급 가죽+", (RecipeOption("상급 가죽+", (
                Ingredient("상급 가죽", 4, True),
                Ingredient("상급 생가죽+", 20, False),
                Ingredient("타닌 가루", 12, False),
            )),)),
            Tier("최상급 가죽", (RecipeOption("최상급 가죽", (
                Ingredient("상급 가죽+", 5, True),
                Ingredient("최상급 생가죽", 20, False),
                Ingredient("타닌 가루", 16, False),
            )),)),
            Tier("최상급 가죽+", (RecipeOption("최상급 가죽+", (
                Ingredient("최상급 가죽", 5, True),
                Ingredient("최상급 생가죽+", 20, False),
                Ingredient("타닌 가루", 20, False),
            )),)),
            Tier("특급 가죽", (RecipeOption("특급 가죽", (
                Ingredient("최상급 가죽+", 5, True),
                Ingredient("특급 생가죽", 20, False),
                Ingredient("타닌 가루", 20, False),
            )),)),
        ),
    ),
    Family(
        key="cloth",
        label="옷감",
        facility="옷감 가공 시설",
        tiers=(
            Tier("옷감", (RecipeOption("옷감", (Ingredient("양털", 10, False, gatherable=True),)),)),
            Tier("옷감+", (RecipeOption("옷감+", (
                Ingredient("옷감", 3, True),
                Ingredient("양털", 4, False, gatherable=True),
            )),)),
            Tier("상급 옷감", (RecipeOption("상급 옷감", (
                Ingredient("옷감+", 3, True),
                Ingredient("상급 양털", 15, False),
                Ingredient("양털", 8, False),
            )),)),
            Tier("상급 옷감+", (RecipeOption("상급 옷감+", (
                Ingredient("상급 옷감", 4, True),
                Ingredient("상급 양털+", 20, False),
                Ingredient("양털", 12, False),
            )),)),
            Tier("최상급 옷감", (RecipeOption("최상급 옷감", (
                Ingredient("상급 옷감+", 5, True),
                Ingredient("최상급 양털", 20, False),
                Ingredient("양털", 16, False),
            )),)),
            Tier("최상급 옷감+", (RecipeOption("최상급 옷감+", (
                Ingredient("최상급 옷감", 5, True),
                Ingredient("최상급 양털+", 20, False),
                Ingredient("양털", 20, False),
            )),)),
            Tier("특급 옷감", (RecipeOption("특급 옷감", (
                Ingredient("최상급 옷감+", 5, True),
                Ingredient("특급 양털", 20, False),
                Ingredient("양털", 20, False),
            )),)),
        ),
    ),
)

# Everything the dashboard/decision logic ever needs a live count for: every tier's output
# name plus every ingredient material name across every family.
ALL_MATERIAL_NAMES: tuple[str, ...] = tuple(
    sorted(
        {tier.name for family in FAMILIES for tier in family.tiers}
        | {ing.material for family in FAMILIES for tier in family.tiers for opt in tier.recipes for ing in opt.inputs}
    )
)


class AlteringRoutineWorker(QThread):
    status = Signal(str)
    blocked = Signal(str)
    stopped = Signal()
    # {"materials": {name: count}, "queue": {family_key: occupied_out_of_7},
    #  "queue_completed": {family_key: how_many_of_those_are_done_and_awaiting_collection}} -
    # emitted whenever any of it changes, so a dashboard window can render without ever calling
    # the CLI itself.
    snapshot = Signal(dict)

    def __init__(self, parent=None, duration_seconds: int | None = None):
        """duration_seconds: if set, the routine stops itself (gracefully, not a `blocked`
        stop) once that many seconds have elapsed since run() started - this is what turns the
        otherwise-infinite routine into a finite JOB (see job_queue.py's "가공무한 1시간").
        Checked between discrete actions only (not mid-call), so the actual overshoot is at
        most whatever single action was in flight - up to ~15min for one execute_gathering."""
        super().__init__(parent)
        self._stop_requested = False
        self._blocked_stop = False
        self._rr_index = 0
        self._materials: dict[str, int] = {}
        self._queue_occupied: dict[str, int] = {}
        self._queue_completed: dict[str, int] = {}
        self._duration_seconds = duration_seconds
        self._start_time: float | None = None
        self._target_lock = threading.Lock()
        self._targets: dict[str, int] = {f.key: f.default_target_idx for f in FAMILIES}

    def request_stop(self) -> None:
        self._stop_requested = True

    def set_target(self, family_key: str, tier_idx: int) -> None:
        """Thread-safe: called from the GUI thread (slider drag) while run() reads it from the
        worker thread. Takes effect from the next round onward (§_target_for)."""
        with self._target_lock:
            self._targets[family_key] = tier_idx

    def _target_for(self, family_key: str) -> int:
        with self._target_lock:
            return self._targets[family_key]

    def _time_exceeded(self) -> bool:
        if self._duration_seconds is None or self._start_time is None:
            return False
        return time.monotonic() - self._start_time >= self._duration_seconds

    def run(self) -> None:
        self._start_time = time.monotonic()
        duration_note = f" - {self._duration_seconds}초 후 자동 종료" if self._duration_seconds else ""
        self.status.emit(f"가공 무한 루틴 시작 (금속/목재/가죽/옷감){duration_note}")
        while not self._stop_requested:
            if self._time_exceeded():
                self.status.emit("⏱️ 설정된 시간이 지나 루틴을 자동 종료합니다")
                break
            try:
                swept = self._sweep_all_facilities()
            except Exception as exc:  # noqa: BLE001 - one bad response shouldn't kill the loop
                swept = False
                self.status.emit(f"⚠️ 예외 발생, 계속 진행: {exc}")
            if self._stop_requested:
                break

            gathered_any = self._gather_until_worth_a_collection_trip()
            if self._stop_requested:
                break

            if not swept and not gathered_any:
                self._sleep_interruptible(TICK_IDLE_SECONDS)
        if not self._blocked_stop:
            self.status.emit("루틴 정지")
        self.stopped.emit()

    def _sleep_interruptible(self, seconds: int) -> None:
        for _ in range(seconds):
            if self._stop_requested:
                return
            self.msleep(1000)

    def _emit_snapshot(self) -> None:
        self.snapshot.emit(
            {
                "materials": dict(self._materials),
                "queue": dict(self._queue_occupied),
                "queue_completed": dict(self._queue_completed),
            }
        )

    # -- round 1: visit every facility, collect it, then fill it to the brim before moving on --

    def _sweep_all_facilities(self) -> bool:
        works = run_cli("get_altering_works", timeout=30)
        if not isinstance(works, dict):
            self.status.emit(f"⚠️ 대기열 조회 실패: {works}")
            return False
        all_works = works.get("works", [])

        self.status.emit("⏳ 재료 재고 확인 중...")
        self._materials = self._inventory_counts()
        self._queue_occupied = {
            family.key: sum(
                1
                for w in all_works
                if w.get("FacilityName") == family.facility and w.get("State") in ("NotStarted", "InProgress", "Completed")
            )
            for family in FAMILIES
        }
        self._queue_completed = {
            family.key: sum(
                1 for w in all_works if w.get("FacilityName") == family.facility and w.get("State") == "Completed"
            )
            for family in FAMILIES
        }
        self._emit_snapshot()

        def is_skipped(family: Family) -> bool:
            if family.skip_below is None:
                return False
            material, minimum = family.skip_below
            return self._materials.get(material, 0) < minimum

        # Rotate which family is visited first each round so no single one is starved.
        order = FAMILIES[self._rr_index :] + FAMILIES[: self._rr_index]
        self._rr_index = (self._rr_index + 1) % len(FAMILIES)

        acted = False
        idle_notes: list[str] = []
        for family in order:
            if is_skipped(family):
                material, minimum = family.skip_below
                idle_notes.append(f"{family.label} 스킵({material} {self._materials.get(material, 0)}개, {minimum}개 미만)")
                continue

            facility_works = [w for w in all_works if w.get("FacilityName") == family.facility]
            completed = [w for w in facility_works if w.get("State") == "Completed"]
            active_count = sum(1 for w in facility_works if w.get("State") in ("NotStarted", "InProgress"))

            remaining_completed = 0
            if completed:
                collected_ok = self._collect(family, completed[0]["DisplayName"])
                if collected_ok:
                    acted = True
                    self._materials = self._inventory_counts()
                else:
                    # Collect failed without being `blocked` (rare) - those completed works are
                    # still sitting there uncollected, still occupying their slots.
                    remaining_completed = len(completed)
                self._queue_occupied[family.key] = active_count + remaining_completed
                self._queue_completed[family.key] = remaining_completed
                self._emit_snapshot()
                if self._stop_requested:
                    return acted

            free_slots = QUEUE_CAPACITY - active_count - remaining_completed
            if free_slots <= 0:
                idle_notes.append(f"{family.label} 대기열 가득")
                continue

            target_idx = self._target_for(family.key)
            plan = self._plan_fill(family, self._materials, free_slots, target_idx)
            if not plan:
                idle_notes.append(f"{family.label} 여유 {free_slots}칸이지만 만들 수 있는 재료 없음")
                continue

            for display_name, log_message, consumption in plan:
                if not self._queue_altering(family, display_name, log_message):
                    break  # blocked or a genuine failure - stop filling this family
                acted = True
                for material, qty in consumption.items():
                    self._materials[material] = self._materials.get(material, 0) - qty
                self._queue_occupied[family.key] = self._queue_occupied.get(family.key, 0) + 1
                self._emit_snapshot()
                if self._stop_requested:
                    return acted

        if not acted and idle_notes:
            self.status.emit("점검 완료, 할 일 없음 - " + " · ".join(idle_notes))
        return acted

    def _plan_one_slot(
        self, family: Family, local: dict[str, int], target_idx: int
    ) -> tuple[str, str, dict[str, int]] | None:
        """Find the highest tier (at or below target_idx) craftable right now. A tier below
        target_idx only spends the excess of its previous tier's stock above
        (N x QUEUE_CAPACITY + PROMOTION_MARGIN) - see module docstring. target_idx itself has
        no reserve; it's the thing the user actually wants stockpiled."""
        for tier_idx in range(target_idx, -1, -1):
            tier = family.tiers[tier_idx]
            for option in tier.recipes:
                consumption: dict[str, int] = {}
                ok = True
                for ing in option.inputs:
                    have = local.get(ing.material, 0)
                    if ing.is_previous_tier:
                        threshold = ing.qty * QUEUE_CAPACITY + PROMOTION_MARGIN
                        if have < threshold + ing.qty:
                            ok = False
                            break
                    elif have < ing.qty:
                        ok = False
                        break
                    consumption[ing.material] = consumption.get(ing.material, 0) + ing.qty
                if not ok:
                    continue
                log_message = (
                    f"[{family.label}] {tier.name} 가공 등록 "
                    f"({', '.join(f'{m} {q}개' for m, q in consumption.items())} 소모)"
                )
                return option.display_name, log_message, consumption
        return None

    def _plan_fill(
        self, family: Family, inv: dict[str, int], free_slots: int, target_idx: int
    ) -> list[tuple[str, str, dict[str, int]]]:
        """Plans against a scratch copy of `inv` (never mutates the caller's dict - the caller
        only applies each step's `consumption` once that step's execute_altering call actually
        succeeds, so an interrupted plan never double-counts stock that was never really spent)."""
        local = dict(inv)
        plan: list[tuple[str, str, dict[str, int]]] = []
        while len(plan) < free_slots:
            step = self._plan_one_slot(family, local, target_idx)
            if step is None:
                break
            display_name, log_message, consumption = step
            for material, qty in consumption.items():
                local[material] = local.get(material, 0) - qty
            plan.append((display_name, log_message, consumption))
        return plan

    # -- round 2: gather whatever's most depleted, in bursts, without constantly detouring ----

    def _gather_until_worth_a_collection_trip(self) -> bool:
        gathered_any = False
        while not self._stop_requested:
            if self._time_exceeded():
                return gathered_any
            target = self._decide_gather(self._materials)
            if target is None:
                return gathered_any
            family, material = target
            # 철 광석/광석 채집지는 이동이 유독 오래 걸린다(사용자 지정) - 한 번 갔으면 그
            # 왕복이 아깝지 않게 목표치 달성 여부와 무관하게 그 자리에서 두 번 연달아 채집.
            repeats = LONG_TRAVEL_GATHER_REPEAT.get(material, 1)
            for _ in range(repeats):
                ok = self._gather(family, material)
                gathered_any = True
                if self._stop_requested or not ok:
                    return gathered_any
            ready = self._count_ready_facilities()
            if ready >= READY_FACILITY_THRESHOLD:
                self.status.emit(f"⏳ {ready}/{len(FAMILIES)}개 시설 회수 가능 - 채집 이어가지 않고 회수+재충전으로 전환")
                return gathered_any
        return gathered_any

    def _decide_gather(self, inv: dict[str, int]) -> tuple[Family, str] | None:
        def is_skipped(family: Family) -> bool:
            if family.skip_below is None:
                return False
            material, minimum = family.skip_below
            return inv.get(material, 0) < minimum

        candidates: list[tuple[float, Family, str]] = []
        for family in FAMILIES:
            if is_skipped(family):
                continue
            for material, qty in family.raw_material_demand().items():
                target = QUEUE_CAPACITY * qty * RAW_MATERIAL_BUFFER_MULTIPLIER
                current = inv.get(material, 0)
                if current < target:
                    candidates.append((current / target, family, material))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])  # most depleted relative to its own target first
        _, family, material = candidates[0]
        return family, material

    def _count_ready_facilities(self) -> int:
        works = run_cli("get_altering_works", timeout=30)
        if not isinstance(works, dict):
            return 0
        all_works = works.get("works", [])
        return sum(
            1
            for family in FAMILIES
            if any(w.get("FacilityName") == family.facility and w.get("State") == "Completed" for w in all_works)
        )

    # -- individual CLI actions -----------------------------------------------

    def _inventory_counts(self) -> dict[str, int]:
        """One get_items call for everything (inventory+account+character storage summed),
        then aggregated locally by name - the 7-tier redesign (2026-09-20) pushed
        ALL_MATERIAL_NAMES from ~15 to ~50+ names, and this used to be one get_items call per
        name (~50 CLI round-trips, ~6s+ of pure latency per round - see
        10_RESEARCH/04_cli_getter_latency_2026-09-20.md). A single unfiltered call is exactly
        as correct (get_items already returns everything when the body is omitted) and turns
        that into 1 call regardless of how many tiers get added later."""
        data = run_cli("get_items", timeout=30)
        counts: dict[str, int] = {name: 0 for name in ALL_MATERIAL_NAMES}
        if isinstance(data, list):
            for item in data:
                name = item.get("DisplayName")
                if name in counts:
                    counts[name] += item.get("Count", 0)
        return counts

    def _collect(self, family: Family, probe_display_name: str) -> bool:
        self.status.emit(f"⏳ [{family.label}] 완료된 가공물 회수 중... (이동 포함)")
        body = json.dumps({"displayName": probe_display_name}, ensure_ascii=False)
        data = run_cli("complete_altering_work", body, timeout=120)
        ok, reason = classify_cli_result(data)
        if ok:
            collected = data.get("collected") if isinstance(data, dict) else None
            self.status.emit(f"✅ [{family.label}] 회수 완료{f' ({collected})' if collected else ''}")
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ [{family.label}] 회수 실패: {reason}")
        return False

    def _queue_altering(self, family: Family, display_name: str, log_message: str) -> bool:
        self.status.emit(f"⏳ [{family.label}] '{display_name}' 가공 등록 중... (이동 포함, 최대 2분)")
        body = json.dumps({"displayName": display_name}, ensure_ascii=False)
        data = run_cli("execute_altering", body, timeout=120)
        ok, reason = classify_cli_result(data)
        if ok:
            self.status.emit(f"🔧 {log_message}")
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ [{family.label}] 가공 등록 실패({display_name}): {reason}")
        return False

    def _gather(self, family: Family, item_name: str) -> bool:
        self.status.emit(f"⏳ [{family.label}] '{item_name}' 채집 중... (약 2분 소요, 최대 15분, 최대 100개)")
        body = json.dumps({"displayName": item_name}, ensure_ascii=False)
        data = run_cli("execute_gathering", body, timeout=900)
        ok, fail_reason = classify_cli_result(data)
        if ok:
            gained = data.get("gained") if isinstance(data, dict) else None
            self.status.emit(f"⛏️ [{family.label}] '{item_name}' 채집 완료{f' ({gained}개)' if gained else ''}")
            if gained:
                self._materials[item_name] = self._materials.get(item_name, 0) + gained
                self._emit_snapshot()
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ [{family.label}] '{item_name}' 채집 실패: {fail_reason}")
        return False

    def _check_blocked(self, data) -> bool:
        kind = data.get("kind") if isinstance(data, dict) else None
        if kind:
            self.blocked.emit(str(kind))
            self._stop_requested = True
            self._blocked_stop = True
            return True
        return False
