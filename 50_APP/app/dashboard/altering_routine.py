"""Generalized '가공 무한' routine: keeps every configured altering facility's 7-slot queue
full forever, across four material chains, following one worker's round-robin loop
(user-specified, 2026-09-18). Replaces the earlier single-material SteelRoutineWorker.

One CLI-calling worker only, sweeping all four facilities every round and gathering whatever
raw material is most needed in between - not four separate workers "in parallel". Running
multiple workers that hit the same MabinogiMobile_CLI.exe process at once causes conflicts
(see CHANGELOG 2026-09-18, "대화 콘솔 제거" entry, on why the gather buttons and this routine
already lock each other out). For the same reason, the standalone dashboard window
(`routine_dashboard.py`) never polls the CLI itself - it only listens to this worker's
`snapshot` signal, which piggybacks on data the worker was already fetching for its own
decisions.

Recipe chains (user-supplied, 2026-09-18; 나무 진액/철 광석/광석/통나무/양털 confirmed
gatherable via get_gatherable_items, 타닌 가루/생가죽 confirmed NOT gatherable - empty result):

    금속 가공 시설  강철괴 x3 <- 철괴 x3 + 석탄 x4          (5min)
                    철괴 x3   <- 철 광석 x10 또는 광석 x20   (30s,  둘 다 채집 가능)
    목재 가공 시설  목재+ x3  <- 목재 x3 + 나무 진액 x4      (5min)
                    목재 x3   <- 통나무 x10                  (30s,  채집 가능)
    옷감 가공 시설  옷감+ x3  <- 옷감 x3 + 양털 x4           (5min)
                    옷감 x3   <- 양털 x10                    (30s,  채집 가능 - 옷감+과
                                                               원재료가 같은 양털 하나뿐이라
                                                               버퍼도 합산해서 관리한다.
                                                               10개는 목재/가죽 체인과 동일한
                                                               구조로 가정한 값 - 양털 재고가
                                                               항상 충분해서 get_alterable_items가
                                                               MissingIngredients를 보여준 적이
                                                               없어 실측 미확인. 다르면 이 10만
                                                               고치면 됨)
    가죽 가공 시설  가죽+ x3  <- 가죽 x3 + 타닌 가루 x4      (5min)
                    가죽 x3   <- 생가죽 x10                  (30s, **채집 불가**)

타닌 가루와 생가죽은 이 루틴이 절대 채집하지 않고 창고 보유분만 소비한다(둘 다 채집 목록에
없음을 확인함). 생가죽 총 보유량(인벤토리+캐릭터창고+계정창고)이 10개(가죽 1회 가공분) 미만
이면 가죽 체인 자체를 매 라운드 건너뛴다 - 사용자 지정.

Scheduling algorithm (user-specified, 2026-09-18, replacing the earlier 1x/2x
intermediate-buffer hysteresis with a simpler greedy-fill + batched-gathering rule):

  1. 빈 슬롯이 있으면 상위 가공(완제품, 예: 강철괴)을 재료가 허락하는 한 최대한 채워넣는다.
     완제품 재료가 떨어지면 남은 빈 슬롯은 하위 가공(중간재, 예: 철괴)으로 끝까지 채운다.
     (`_plan_fill` - 상위를 먼저 다 밀어넣고, 그다음에야 하위로 넘어간다. 되돌아가지 않는다.)
  2. 시설을 한 바퀴 돌 때는 시설 A를 회수하고 바로 A를 끝까지 채운 다음 시설 B로 넘어간다 -
     회수만 4곳 다 먼저 하고 채우기를 나중에 4곳 다 하는 식이 아니다(`_sweep_all_facilities`).
  3. 채집(`execute_gathering`)은 한 번에 최대 100개까지 채운다. 한 번의 채집이 끝나면 무조건
     다음 채집으로 넘어가지 않고, 완료된 시설이 몇 곳인지 확인한다(`_count_ready_facilities`).
     4곳 중 3곳 이상이 회수 가능한 상태면 회수+재충전 라운드(2번 규칙)를 먼저 하고 나서 다음
     채집으로 넘어간다 - 3곳 미만이면 회수하러 가는 왕복이 아직 아깝다고 보고 채집을 계속한다.

원자재(석탄/철 광석/광석/통나무/양털) 자체를 "언제 채집할지"는 7작업분(`RAW_MATERIAL_BUFFER_MULTIPLIER`
배, 2026-09-18 기준 5배)에 못 미치면 그 재료가 채집 후보에 오르는 방식이다(`_decide_gather` -
여러 체인 중 목표치 대비 가장 많이 모자란 것부터, 목표치에 도달할 때까지 계속). 처음엔 1배
"긴급 기준"과 2배 "목표치"를 나눠뒀었는데, 실제로는 1배만 넘기면 바로 채집 후보에서 빠져서
목표치가 사실상 아무 효과가 없었다 - 강철괴류 작업이 5분 걸리는 동안 채집할 게 금방 바닥나서
캐릭터가 노는 시간이 길어짐(사용자 피드백, 2026-09-18) - 그래서 두 단계를 없애고 이 배수 하나로
"도달할 때까지 계속 채집"으로 단순화했다. 가공 자체는 이 버퍼로 속도를 늦추지 않는다 - 위 1번
규칙대로 상위/하위 가리지 않고 재료가 있는 한 무조건 끝까지 채운다.

대기열 슬롯 계산: `get_altering_works`의 "Completed"(완료했지만 아직 회수 안 한) 항목도 7칸 중
하나를 그대로 차지한다(회수해야 비로소 비워짐) - 회수 자체가 `blocked`는 아니지만 실패하는
드문 경우, 그 완료분은 여전히 슬롯을 점유한 것으로 계산해야 다음 채우기가 실제로 없는 슬롯에
등록을 시도하는 사고를 피할 수 있다.

Runs in its own QThread since execute_gathering/execute_altering block for real minutes at a
time - only ever touches the GUI through signals. Stops itself - rather than looping through
it - the moment any call comes back `blocked` (a confirmation popup, an interrupting dialog,
etc.), consistent with 00_SPEC/03_requirements.md's safeguard requirement, and always leaves
a way for the user to regain control (the Stop button). Does not track a 정령의 날개 daily
budget cap yet (00_SPEC calls for one) - every gather/alter call costs 5, uncapped.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from ..cli_client import run_cli
from .widgets import classify_cli_result

QUEUE_CAPACITY = 7
END_INTERMEDIATE_QTY = 3  # every end product needs 3 of its intermediate, per work

TICK_IDLE_SECONDS = 8
READY_FACILITY_THRESHOLD = 3  # out of 4 - see scheduling rule 3 in the module docstring
# How many 7-work batches worth of each gatherable raw material to stockpile before a gather
# trip for it is no longer "worth it". Raised from 2 to 5 (2026-09-18, user request) after
# noticing the character sat idle a lot: a 강철괴-tier work cooks for ~5min, a gather trip for
# ~2min, but the old 2x target got satisfied by a single 100-unit gather almost immediately,
# so there was nothing left to do with the rest of that 5-minute cook time. At 5x the routine
# keeps chaining gather trips through most of that dead time instead of just sitting there.
RAW_MATERIAL_BUFFER_MULTIPLIER = 5
# 철 광석/광석 채집 지점은 유독 왕복이 오래 걸린다는 사용자 피드백(2026-09-18) - 이 둘을 캐러
# 갈 때는 목표치에 이미 도달했는지와 무관하게 그 자리에서 두 번 연달아 채집(execute_gathering
# x2, 최대 200개)해서 이동 시간을 낭비하지 않는다. 다른 재료는 이동이 짧아 그대로 1회.
LONG_TRAVEL_GATHER_REPEAT: dict[str, int] = {"철 광석": 2, "광석": 2}


@dataclass(frozen=True)
class IntermediatePath:
    """One way to craft a chain's intermediate item from a raw material."""

    recipe: str  # exact display name to pass to execute_altering
    raw_material: str
    raw_qty: int  # needed per one work of `recipe`
    gatherable: bool = True


@dataclass(frozen=True)
class Chain:
    key: str
    label: str  # short tag used in status messages
    facility: str
    end_product: str
    end_direct_material: str
    end_direct_qty: int
    end_direct_gatherable: bool
    intermediate: str
    paths: tuple[IntermediatePath, ...]
    skip_below: tuple[str, int] | None = None  # (material, min_total) - skip chain if under

    def raw_material_demand(self) -> dict[str, int]:
        """Gatherable raw materials this chain needs, summed per one round of 7 works."""
        demand: dict[str, int] = {}
        if self.end_direct_gatherable:
            demand[self.end_direct_material] = demand.get(self.end_direct_material, 0) + self.end_direct_qty
        for path in self.paths:
            if path.gatherable:
                demand[path.raw_material] = demand.get(path.raw_material, 0) + path.raw_qty
        return demand


CHAINS: tuple[Chain, ...] = (
    Chain(
        key="steel",
        label="강철괴",
        facility="금속 가공 시설",
        end_product="강철괴",
        end_direct_material="석탄",
        end_direct_qty=4,
        end_direct_gatherable=True,
        intermediate="철괴",
        paths=(
            IntermediatePath("철괴(철 광석)", "철 광석", 10),
            IntermediatePath("철괴(광석)", "광석", 20),
        ),
    ),
    Chain(
        key="wood",
        label="목재+",
        facility="목재 가공 시설",
        end_product="목재+",
        end_direct_material="나무 진액",
        end_direct_qty=4,
        end_direct_gatherable=True,
        intermediate="목재",
        paths=(IntermediatePath("목재", "통나무", 10),),
    ),
    Chain(
        key="cloth",
        label="옷감+",
        facility="옷감 가공 시설",
        end_product="옷감+",
        end_direct_material="양털",
        end_direct_qty=4,
        end_direct_gatherable=True,
        intermediate="옷감",
        paths=(IntermediatePath("옷감", "양털", 10),),
    ),
    Chain(
        key="leather",
        label="가죽+",
        facility="가죽 가공 시설",
        end_product="가죽+",
        end_direct_material="타닌 가루",
        end_direct_qty=4,
        end_direct_gatherable=False,
        intermediate="가죽",
        paths=(IntermediatePath("가죽", "생가죽", 10, gatherable=False),),
        skip_below=("생가죽", 10),
    ),
)

END_PRODUCTS: tuple[str, ...] = tuple(c.end_product for c in CHAINS)

# Everything the dashboard/decision logic ever needs a live count for: end products,
# intermediates, and every raw material (gatherable or not).
ALL_MATERIAL_NAMES: tuple[str, ...] = tuple(
    sorted(
        {c.intermediate for c in CHAINS}
        | {c.end_direct_material for c in CHAINS}
        | {p.raw_material for c in CHAINS for p in c.paths}
        | set(END_PRODUCTS)
    )
)


class AlteringRoutineWorker(QThread):
    status = Signal(str)
    blocked = Signal(str)
    stopped = Signal()
    # {"materials": {name: count}, "queue": {chain_key: occupied_out_of_7},
    #  "queue_completed": {chain_key: how_many_of_those_are_done_and_awaiting_collection}} -
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

    def request_stop(self) -> None:
        self._stop_requested = True

    def _time_exceeded(self) -> bool:
        if self._duration_seconds is None or self._start_time is None:
            return False
        return time.monotonic() - self._start_time >= self._duration_seconds

    def run(self) -> None:
        self._start_time = time.monotonic()
        duration_note = f" - {self._duration_seconds}초 후 자동 종료" if self._duration_seconds else ""
        self.status.emit(f"가공 무한 루틴 시작 (강철괴/목재+/옷감+/가죽+){duration_note}")
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
            chain.key: sum(
                1
                for w in all_works
                if w.get("FacilityName") == chain.facility and w.get("State") in ("NotStarted", "InProgress", "Completed")
            )
            for chain in CHAINS
        }
        self._queue_completed = {
            chain.key: sum(
                1 for w in all_works if w.get("FacilityName") == chain.facility and w.get("State") == "Completed"
            )
            for chain in CHAINS
        }
        self._emit_snapshot()

        def is_skipped(chain: Chain) -> bool:
            if chain.skip_below is None:
                return False
            material, minimum = chain.skip_below
            return self._materials.get(material, 0) < minimum

        # Rotate which chain is visited first each round so no single chain is starved.
        order = CHAINS[self._rr_index :] + CHAINS[: self._rr_index]
        self._rr_index = (self._rr_index + 1) % len(CHAINS)

        acted = False
        idle_notes: list[str] = []
        for chain in order:
            if is_skipped(chain):
                material, minimum = chain.skip_below
                idle_notes.append(f"{chain.label} 스킵({material} {self._materials.get(material, 0)}개, {minimum}개 미만)")
                continue

            facility_works = [w for w in all_works if w.get("FacilityName") == chain.facility]
            completed = [w for w in facility_works if w.get("State") == "Completed"]
            active_count = sum(1 for w in facility_works if w.get("State") in ("NotStarted", "InProgress"))

            remaining_completed = 0
            if completed:
                collected_ok = self._collect(chain, completed[0]["DisplayName"])
                if collected_ok:
                    acted = True
                    self._materials[chain.end_product] = self._fetch_count(chain.end_product)
                else:
                    # Collect failed without being `blocked` (rare) - those completed works are
                    # still sitting there uncollected, still occupying their slots.
                    remaining_completed = len(completed)
                self._queue_occupied[chain.key] = active_count + remaining_completed
                self._queue_completed[chain.key] = remaining_completed
                self._emit_snapshot()
                if self._stop_requested:
                    return acted

            free_slots = QUEUE_CAPACITY - active_count - remaining_completed
            if free_slots <= 0:
                idle_notes.append(f"{chain.label} 대기열 가득")
                continue

            plan = self._plan_fill(chain, self._materials, free_slots)
            if not plan:
                blocker = (
                    chain.paths[0].raw_material
                    if self._materials.get(chain.intermediate, 0) < END_INTERMEDIATE_QTY
                    else chain.end_direct_material
                )
                idle_notes.append(f"{chain.label} 여유 {free_slots}칸이지만 {blocker} {self._materials.get(blocker, 0)}개뿐")
                continue

            for display_name, log_message, consumption in plan:
                if not self._queue_altering(chain, display_name, log_message):
                    break  # blocked or a genuine failure - stop filling this chain
                acted = True
                for material, qty in consumption.items():
                    self._materials[material] = self._materials.get(material, 0) - qty
                self._queue_occupied[chain.key] = self._queue_occupied.get(chain.key, 0) + 1
                self._emit_snapshot()
                if self._stop_requested:
                    return acted

        if not acted and idle_notes:
            self.status.emit("점검 완료, 할 일 없음 - " + " · ".join(idle_notes))
        return acted

    def _plan_fill(
        self, chain: Chain, inv: dict[str, int], free_slots: int
    ) -> list[tuple[str, str, dict[str, int]]]:
        """Greedily plan up to `free_slots` altering calls for one chain: push the end product
        as far as currently-owned stock allows, then spend any remaining slots on the
        intermediate - never the reverse. Plans against a scratch copy of `inv` (never mutates
        the caller's dict - the caller only applies each step's `consumption` once that step's
        execute_altering call actually succeeds, so an interrupted plan never double-counts
        stock that was never really spent)."""
        local = dict(inv)
        plan: list[tuple[str, str, dict[str, int]]] = []

        while len(plan) < free_slots:
            if local.get(chain.intermediate, 0) < END_INTERMEDIATE_QTY or local.get(chain.end_direct_material, 0) < chain.end_direct_qty:
                break
            local[chain.intermediate] -= END_INTERMEDIATE_QTY
            local[chain.end_direct_material] -= chain.end_direct_qty
            plan.append(
                (
                    chain.end_product,
                    f"[{chain.label}] {chain.end_product} 가공 등록 ({len(plan) + 1}/{free_slots}번째, "
                    f"{chain.intermediate}/{chain.end_direct_material} 소모)",
                    {chain.intermediate: END_INTERMEDIATE_QTY, chain.end_direct_material: chain.end_direct_qty},
                )
            )

        while len(plan) < free_slots:
            path = next((p for p in chain.paths if local.get(p.raw_material, 0) >= p.raw_qty), None)
            if path is None:
                break
            local[path.raw_material] -= path.raw_qty
            plan.append(
                (
                    path.recipe,
                    f"[{chain.label}] {chain.intermediate} 가공 등록 - {path.raw_material} 사용 "
                    f"({len(plan) + 1}/{free_slots}번째, 상위 재료 소진)",
                    {path.raw_material: path.raw_qty},
                )
            )

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
            chain, material = target
            # 철 광석/광석 채집지는 이동이 유독 오래 걸린다(사용자 지정) - 한 번 갔으면 그
            # 왕복이 아깝지 않게 목표치 달성 여부와 무관하게 그 자리에서 두 번 연달아 채집.
            repeats = LONG_TRAVEL_GATHER_REPEAT.get(material, 1)
            for _ in range(repeats):
                ok = self._gather(chain, material)
                gathered_any = True
                if self._stop_requested or not ok:
                    return gathered_any
            ready = self._count_ready_facilities()
            if ready >= READY_FACILITY_THRESHOLD:
                self.status.emit(f"⏳ {ready}/{len(CHAINS)}개 시설 회수 가능 - 채집 이어가지 않고 회수+재충전으로 전환")
                return gathered_any
        return gathered_any

    def _decide_gather(self, inv: dict[str, int]) -> tuple[Chain, str] | None:
        def is_skipped(chain: Chain) -> bool:
            if chain.skip_below is None:
                return False
            material, minimum = chain.skip_below
            return inv.get(material, 0) < minimum

        candidates: list[tuple[float, Chain, str]] = []
        for chain in CHAINS:
            if is_skipped(chain):
                continue
            for material, qty in chain.raw_material_demand().items():
                target = QUEUE_CAPACITY * qty * RAW_MATERIAL_BUFFER_MULTIPLIER
                current = inv.get(material, 0)
                if current < target:
                    candidates.append((current / target, chain, material))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])  # most depleted relative to its own target first
        _, chain, material = candidates[0]
        return chain, material

    def _count_ready_facilities(self) -> int:
        works = run_cli("get_altering_works", timeout=30)
        if not isinstance(works, dict):
            return 0
        all_works = works.get("works", [])
        return sum(
            1
            for chain in CHAINS
            if any(w.get("FacilityName") == chain.facility and w.get("State") == "Completed" for w in all_works)
        )

    # -- individual CLI actions -----------------------------------------------

    def _fetch_count(self, name: str) -> int:
        data = run_cli("get_items", json.dumps({"name": name}, ensure_ascii=False), timeout=30)
        return sum(item.get("Count", 0) for item in data if item.get("DisplayName") == name) if isinstance(data, list) else 0

    def _inventory_counts(self) -> dict[str, int]:
        return {name: self._fetch_count(name) for name in ALL_MATERIAL_NAMES}

    def _collect(self, chain: Chain, probe_display_name: str) -> bool:
        self.status.emit(f"⏳ [{chain.label}] 완료된 가공물 회수 중... (이동 포함)")
        body = json.dumps({"displayName": probe_display_name}, ensure_ascii=False)
        data = run_cli("complete_altering_work", body, timeout=120)
        ok, reason = classify_cli_result(data)
        if ok:
            collected = data.get("collected") if isinstance(data, dict) else None
            self.status.emit(f"✅ [{chain.label}] 회수 완료{f' ({collected})' if collected else ''}")
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ [{chain.label}] 회수 실패: {reason}")
        return False

    def _queue_altering(self, chain: Chain, display_name: str, log_message: str) -> bool:
        self.status.emit(f"⏳ [{chain.label}] '{display_name}' 가공 등록 중... (이동 포함, 최대 2분)")
        body = json.dumps({"displayName": display_name}, ensure_ascii=False)
        data = run_cli("execute_altering", body, timeout=120)
        ok, reason = classify_cli_result(data)
        if ok:
            self.status.emit(f"🔧 {log_message}")
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ [{chain.label}] 가공 등록 실패({display_name}): {reason}")
        return False

    def _gather(self, chain: Chain, item_name: str) -> bool:
        self.status.emit(f"⏳ [{chain.label}] '{item_name}' 채집 중... (약 2분 소요, 최대 15분, 최대 100개)")
        body = json.dumps({"displayName": item_name}, ensure_ascii=False)
        data = run_cli("execute_gathering", body, timeout=900)
        ok, fail_reason = classify_cli_result(data)
        if ok:
            gained = data.get("gained") if isinstance(data, dict) else None
            self.status.emit(f"⛏️ [{chain.label}] '{item_name}' 채집 완료{f' ({gained}개)' if gained else ''}")
            if gained:
                self._materials[item_name] = self._materials.get(item_name, 0) + gained
                self._emit_snapshot()
            return True
        if self._check_blocked(data):
            return False
        self.status.emit(f"⚠️ [{chain.label}] '{item_name}' 채집 실패: {fail_reason}")
        return False

    def _check_blocked(self, data) -> bool:
        kind = data.get("kind") if isinstance(data, dict) else None
        if kind:
            self.blocked.emit(str(kind))
            self._stop_requested = True
            self._blocked_stop = True
            return True
        return False
