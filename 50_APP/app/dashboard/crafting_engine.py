"""Prepare live recipe shortages before crafting; retain confirmed progress.

The connector lists shortages for ONE craft, not the complete ingredient bill.
Known ingredients are aggregated across the entire remaining dependency graph.
Facility slots are filled to the needed quantity, crediting in-flight production.
While facilities work, the single CLI worker prepares other independent materials.
Undisclosed requirements cannot be multiplied, so each craft is revalidated.
"""
from __future__ import annotations

import copy
import json
import math
import time
from PySide6.QtCore import QThread, Signal
from ..cli_client import run_cli
from .recipe_variants import choose_recipe_variant, distinct_recipe_variants
from .altering_routine import FAMILIES, QUEUE_CAPACITY


class CraftingError(RuntimeError):
    pass


class _Paused(Exception):
    pass


# Exact output/recipe relationships documented in altering_routine.FAMILIES.
# Never infer output names by stripping parentheses from arbitrary recipes.
ALTERING_RECIPES = {"철괴": ("철괴(철 광석)", "철괴(광석)")}
REASONS = {
    "insufficient_living_skill_level": "생활 스킬 레벨이 부족합니다",
    "insufficient_facility_level": "생산 시설 레벨이 부족합니다",
    "insufficient_decor_score": "데코 점수가 부족합니다",
    "ingredient_locked": "재료가 잠겨 있습니다",
    "insufficient_transfer_cost": "창고 재료 이동 비용이 부족합니다",
    "not_enough_currency": "정령의 날개가 부족합니다",
    "requires_user_interaction": "게임에서 직접 시작해야 하는 가공입니다",
}
STAGES = {"preparing": "재료 준비", "gathering": "채집", "processing": "가공",
          "collecting": "생산물 회수", "crafting": "제작", "completed": "완료",
          "paused": "일시정지", "blocked": "확인 필요"}


def positive(value):
    return type(value) is int and value > 0


def unpack(data):
    """Handle both flattened CLI replies and documented response envelopes."""
    if isinstance(data, dict) and isinstance(data.get("body"), (dict, list)):
        if isinstance(data["body"], dict):
            return {"status": data.get("status", "accepted"), **data["body"]}
        if data.get("status", "accepted") == "accepted":
            return data["body"]
    return data


def failure(data):
    if isinstance(data, dict) and (data.get("error") or data.get("pipe") == "disconnected" or data.get("status", "accepted") != "accepted"):
        reason = str(data.get("error") or data.get("reason") or data.get("status") or "연결 확인 필요")
        detail = data.get("kind") or data.get("message")
        return REASONS.get(reason, reason) + (f" · {detail}" if detail else "")
    return None


class CraftingWorker(QThread):
    status = Signal(str)
    blocked = Signal(str)
    progress = Signal(object)
    stopped = Signal()
    POLL_SECONDS = 5
    MAX_WAIT_SECONDS = 21600
    NO_PROGRESS_SECONDS = 600

    def __init__(self, recipe: str, target: int, parent=None):
        super().__init__(parent)
        if not recipe or not positive(target):
            raise ValueError("레시피 이름과 1 이상의 목표 수량이 필요합니다.")
        self.recipe, self.target, self.remaining = recipe, target, target
        self.checkpoint = {"version": 2, "recipe": recipe, "target": target,
                           "completed": 0, "pending": None, "waiting": None, "fishing": None,
                           "observed": {}, "productions": {}, "facilities": {}}
        self._stop_requested = False
        self._materials = {}
        self._work_watch = {}
        self._choice_messages = {}

    def request_stop(self):
        # In-flight CLI actions finish before another queue worker starts.
        # Fishing is stopped explicitly by its finally block.
        self._stop_requested = True

    def _check_stop(self):
        if self._stop_requested:
            raise _Paused()

    def _sleep(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._check_stop()
            self.msleep(min(250, max(1, int((deadline - time.monotonic()) * 1000))))

    def _emit(self, stage, message):
        self.status.emit(message)
        self.progress.emit({"recipe": self.recipe, "target": self.target,
            "completed": self.target - self.remaining, "stage": STAGES.get(stage, stage),
            "materials": copy.deepcopy(list(self._materials.values())), "message": message,
            "material_scope": "확인된 재료는 남은 목표 전량 · 생산 중 수량을 포함해 필요한 만큼 준비"})

    def _material(self, name, owned, required, state, remaining_seconds=None):
        row = {"name": name, "owned": owned, "required": required, "state": state}
        if remaining_seconds is not None:
            row["remaining_seconds"] = remaining_seconds
        self._materials[name] = row

    def _query(self, command, body=None, *, check_stop=True):
        if check_stop:
            self._check_stop()
        data = unpack(run_cli(command, body, timeout=30))
        error = failure(data)
        if error:
            raise CraftingError(error)
        return data

    def _items(self, command):
        data = self._query(command)
        if isinstance(data, dict) and data.get("craftingUnlocked") is False:
            raise CraftingError("제작 시스템이 아직 해금되지 않았습니다.")
        rows = data if isinstance(data, list) else data.get("items") if isinstance(data, dict) else None
        if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
            raise CraftingError(f"{command}: 목록을 확인하지 못했습니다.")
        return rows

    def _exact(self, rows, name, *, command=None, material_cost=None):
        matches = distinct_recipe_variants(
            [row for row in rows if row.get("DisplayName") == name]
        )
        if not matches:
            return None
        if command is None:
            command = ("get_alterable_items" if any("Alterable" in row for row in matches)
                       else "get_craftable_items" if any("Craftable" in row for row in matches)
                       else "get_gatherable_items")
        key = command + ":" + name
        if len(matches) > 1:
            self.checkpoint.setdefault("variant_names", {})[key] = True
        selected = choose_recipe_variant(matches,
            desired=self.remaining if name == self.recipe and command == "get_craftable_items" else None,
            material_cost=material_cost)
        if selected is None:
            return None
        if self.checkpoint.get("variant_names", {}).get(key):
            selected["_catalog_auto_choice"] = True
            missing = selected.get("MissingIngredients") or []
            inputs = ", ".join(str(item.get("DisplayName", "")) for item in missing if isinstance(item, dict))
            decision = "보유 재료로 진행" if self._ready(selected, command == "get_alterable_items") else (inputs or "조건 확인")
            if self._choice_messages.get(key) != decision:
                self._choice_messages[key] = decision
                self._emit("preparing", f"{name} · 제작법 자동 비교: {decision}")
        return selected

    def _recipe(self, command, name):
        rows = self._items(command)
        matching = [row for row in rows if row.get("DisplayName") == name]
        cost = None
        if len(distinct_recipe_variants(matching)) > 1 and not any(self._ready(row, command == "get_alterable_items") for row in matching):
            gather_rows = self._items("get_gatherable_items")
            alter_rows = rows if command == "get_alterable_items" else self._items("get_alterable_items")
            craft_rows = rows if command == "get_craftable_items" else self._items("get_craftable_items")
            cost = self._material_cost(gather_rows, alter_rows, craft_rows)
        found = self._exact(rows, name, command=command, material_cost=cost)
        if found is None:
            raise CraftingError(f"{name}: 게임의 레시피 목록에서 정확한 이름을 찾지 못했습니다.")
        return found

    def _material_cost(self, gather_rows, alter_rows, craft_rows):
        """A preparation estimate from current public shortage data, not prices.

        MissingIngredients only exposes insufficient inputs. A ready route costs
        one action; direct gathering costs one action plus needed units. Cycles,
        unavailable conditions and materials without an automatic path are last.
        """
        def estimate(name, quantity, stack=()):
            if quantity <= 0:
                return 0.0
            if name in stack or len(stack) >= 16:
                return math.inf
            if any(row.get("DisplayName") == name and row.get("ToolOk") is True for row in gather_rows):
                return 1.0 + quantity
            candidates = [(row, True) for row in alter_rows
                          if row.get("DisplayName") in (name, *ALTERING_RECIPES.get(name, ()))]
            candidates += [(row, False) for row in craft_rows if row.get("DisplayName") == name]
            costs = []
            for row, altering in candidates:
                produced = row.get("ProducedPerWork" if altering else "ProducedPerCraft")
                if not positive(produced):
                    continue
                batches = math.ceil(quantity / produced)
                if self._ready(row, altering):
                    costs.append(float(batches))
                    continue
                missing = row.get("MissingIngredients")
                if row.get("Reason") != "not_enough_ingredient" or not isinstance(missing, list) or not missing:
                    continue
                cost = float(batches)
                for ingredient in missing:
                    if not isinstance(ingredient, dict) or not ingredient.get("DisplayName") or not positive(ingredient.get("Required")):
                        cost = math.inf
                        break
                    stock = ingredient.get("Owned", 0)
                    stock = stock if type(stock) is int and stock >= 0 else 0
                    deficit = max(0, ingredient["Required"] * batches - stock)
                    cost += estimate(ingredient["DisplayName"], deficit, (*stack, name))
                costs.append(cost)
            return min(costs, default=math.inf)
        return estimate

    def _owned(self, name, *, after_action=False):
        data = self._query("get_items", json.dumps({"name": name}, ensure_ascii=False), check_stop=not after_action)
        rows = data if isinstance(data, list) else data.get("items") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise CraftingError(f"{name}: 보유량을 확인하지 못했습니다.")
        total = 0
        for row in rows:
            if not isinstance(row, dict):
                raise CraftingError(f"{name}: 보유량 응답이 올바르지 않습니다.")
            if row.get("DisplayName") == name and not row.get("IsLocked", False):
                count = row.get("Count")
                if type(count) is not int or count < 0:
                    raise CraftingError(f"{name}: 보유 수량을 확인하지 못했습니다.")
                total += count
        return total

    def _action(self, command, name, expected, **extra):
        self._check_stop()
        if self.checkpoint.get("pending"):
            raise CraftingError("직전 동작 결과가 확인되지 않았습니다. 게임에서 결과를 확인해주세요.")
        self.checkpoint["pending"] = {"command": command, "name": name}
        data = unpack(run_cli(command, json.dumps({"displayName": name, **extra}, ensure_ascii=False), timeout=900))
        error = failure(data)
        if error:
            # Only an explicit pre-start rejection proves no item was made.
            if isinstance(data, dict) and data.get("status") in ("rejected", "invalid_body"):
                self.checkpoint["pending"] = None
            suffix = "" if not self.checkpoint["pending"] else " · 결과 미확인으로 자동 재실행하지 않습니다."
            raise CraftingError(f"{name}: {error}{suffix}")
        if isinstance(data, dict) and data.get("result") == "stopped_by_user":
            self.checkpoint["pending"] = None
            raise CraftingError(f"{name}: 게임에서 작업을 중지했습니다.")
        if not isinstance(data, dict) or (expected and data.get("result") not in expected):
            raise CraftingError(f"{name}: 동작 완료를 확인하지 못했습니다. 자동 재실행하지 않습니다.")
        return data

    def _learn_requirements(self, command, row):
        """Keep observed quantities when sufficient stock hides them next time.

        No complete bill is exposed by the connector. This is knowledge from
        actual shortage replies only, never an inferred/guessed game recipe.
        """
        name = row["DisplayName"]
        key = command + ":" + name
        if row.get("_catalog_auto_choice") or self.checkpoint.get("variant_names", {}).get(key):
            # The API hides sufficient ingredients and has no stable variant ID.
            # Never union mutually exclusive recipes under the same display name.
            self.checkpoint.setdefault("observed", {}).pop(key, None)
            if name == self.recipe and command == "get_craftable_items":
                self.checkpoint.pop("requirements", None)
            current = {}
            missing = row.get("MissingIngredients", [])
            if not isinstance(missing, list):
                raise CraftingError(f"{name}: 부족한 재료 정보를 확인하지 못했습니다.")
            for ingredient in missing:
                if not isinstance(ingredient, dict) or not ingredient.get("DisplayName") or not positive(ingredient.get("Required")):
                    raise CraftingError(f"{name}: 재료 수량 정보가 올바르지 않습니다.")
                current[ingredient["DisplayName"]] = ingredient["Required"]
            return current
        known = self.checkpoint.setdefault("observed", {}).setdefault(key, {})
        if name == self.recipe and command == "get_craftable_items":
            known.update(self.checkpoint.get("requirements", {}))
        missing = row.get("MissingIngredients", [])
        if not isinstance(missing, list):
            raise CraftingError(f"{name}: 부족한 재료 정보를 확인하지 못했습니다.")
        for ingredient in missing:
            if (not isinstance(ingredient, dict) or not ingredient.get("DisplayName")
                    or not positive(ingredient.get("Required"))):
                raise CraftingError(f"{name}: 재료 수량 정보가 올바르지 않습니다.")
            known[ingredient["DisplayName"]] = ingredient["Required"]
        if name == self.recipe and command == "get_craftable_items":
            self.checkpoint["requirements"] = dict(known)
        return known

    @staticmethod
    def _ready(row, altering=False):
        return row.get("Alterable" if altering else "Craftable") is True

    def _validate_recipe(self, row, altering=False):
        if not self._ready(row, altering):
            reason = row.get("Reason")
            if reason != "not_enough_ingredient":
                raise CraftingError(f"{row['DisplayName']}: {REASONS.get(reason, reason or '제작 조건을 확인해주세요')}")
            if not row.get("MissingIngredients"):
                raise CraftingError(f"{row['DisplayName']}: 부족한 재료 정보를 확인하지 못했습니다.")
        output = row.get("ProducedPerWork" if altering else "ProducedPerCraft")
        if not positive(output):
            raise CraftingError(f"{row['DisplayName']}: 1회 생산량을 확인하지 못했습니다.")
        return output

    def _facility(self, recipe, row=None):
        if row and isinstance(row.get("FacilityName"), str) and row["FacilityName"]:
            return row["FacilityName"]
        observed = self.checkpoint.setdefault("facilities", {}).get(recipe)
        if observed:
            return observed
        for family in FAMILIES:
            if any(recipe == option.display_name for tier in family.tiers for option in tier.recipes):
                return family.facility
        return None

    def _learn_facilities(self, works):
        by_recipe = {}
        for work in works:
            name, facility = work.get("DisplayName"), work.get("FacilityName")
            if isinstance(name, str) and isinstance(facility, str) and facility:
                by_recipe.setdefault(name, set()).add(facility)
        for name, facilities in by_recipe.items():
            if len(facilities) == 1:
                self.checkpoint.setdefault("facilities", {})[name] = next(iter(facilities))

    @staticmethod
    def _completed(work):
        return work.get("IsCompleted") is True or work.get("State") == "Completed"

    @staticmethod
    def _works_signature(works):
        return tuple(sorted((str(work.get("DisplayName")), str(work.get("FacilityName")),
                             str(work.get("State")), str(work.get("RemainingSeconds")),
                             str(work.get("IsCompleted"))) for work in works))

    def _migrate_production_checkpoint(self):
        self.checkpoint.setdefault("observed", {})
        self.checkpoint.setdefault("facilities", {})
        tracked = self.checkpoint.setdefault("productions", {})
        waiting = self.checkpoint.get("waiting")
        if isinstance(waiting, dict) and waiting.get("recipe") and waiting.get("product"):
            tracked.setdefault(waiting["recipe"], dict(waiting))
        self.checkpoint["version"] = 2

    def _sync_legacy_waiting(self):
        # Retain the old single-waiting key for already saved queue checkpoints.
        tracked = self.checkpoint.get("productions", {})
        self.checkpoint["waiting"] = copy.deepcopy(next(iter(tracked.values()), None))

    def _track_work(self, product, recipe, owned, required, produced, *, registered=False, baseline_count=0):
        tracked = self.checkpoint.setdefault("productions", {})
        entry = tracked.setdefault(recipe, {"product": product, "recipe": recipe,
                                            "before": owned, "required": required})
        entry.update(required=required, produced=produced)
        if registered:
            # A confirmed 'started' without a visible queue row is still supply.
            # Do not retry the operation simply because a later query lags.
            entry["unobserved"] = entry.get("unobserved", 0) + 1
            entry["registration_count"] = baseline_count
            entry["registration_owned"] = owned
        self._sync_legacy_waiting()

    def _reconcile_productions(self, works, owned):
        tracked = self.checkpoint.setdefault("productions", {})
        now = time.monotonic()
        for recipe, entry in list(tracked.items()):
            matching = [work for work in works if work.get("DisplayName") == recipe]
            stock = owned(entry["product"])
            provisional = entry.get("unobserved", 0)
            if provisional:
                expected_count = entry.get("registration_count", 0) + provisional
                absent = max(0, expected_count - len(matching))
                collected_since_registration = stock - entry.get("registration_owned", stock)
                if not absent or (positive(entry.get("produced")) and collected_since_registration >= absent * entry["produced"]):
                    entry["unobserved"] = 0
            if matching:
                entry["seen"] = True
            elif not entry.get("unobserved") and stock > entry.get("before", stock):
                del tracked[recipe]
                self._work_watch.pop(recipe, None)
                continue
            elif entry.get("seen") and not entry.get("unobserved"):
                raise CraftingError(f"{recipe}: 등록했던 생산 작업과 생산물을 찾지 못했습니다. 시설을 확인해주세요.")
            signature = self._works_signature(matching)
            watch = self._work_watch.setdefault(recipe, {"started": now, "changed": now, "signature": signature})
            if signature != watch["signature"]:
                watch.update(changed=now, signature=signature)
            queued_only = bool(matching) and all(work.get("State") == "NotStarted" for work in matching)
            if now - watch["started"] > self.MAX_WAIT_SECONDS:
                raise CraftingError(f"{recipe}: 생산 대기 시간을 초과했습니다. 대기열은 보존됩니다.")
            if not queued_only and now - watch["changed"] > self.NO_PROGRESS_SECONDS:
                raise CraftingError(f"{recipe}: 생산 진행 정보가 갱신되지 않습니다. 시설을 확인해주세요.")
        self._sync_legacy_waiting()

    def _plan_materials(self, final_row):
        """Aggregate a DAG of current demands, deducting all queued output.

        An incremental expansion is important for diamonds: the same raw item
        may be needed by a final recipe and several intermediate recipes. Each
        additional batch adds its inputs once, with no double-counted reserve.
        """
        final_output = self._validate_recipe(final_row)
        if self.remaining % final_output:
            raise CraftingError(f"{self.recipe}: 1회 {final_output}개씩 생산됩니다. 목표 수량을 {final_output}의 배수로 설정해주세요.")
        final_requirements = self._learn_requirements("get_craftable_items", final_row)
        final_needs = {name: quantity * (self.remaining // final_output)
                       for name, quantity in final_requirements.items()}
        if not final_needs and not self.checkpoint.get("productions"):
            return {"final": final_row, "needs": {}, "routes": {}, "owned": {}, "works": [], "final_needs": {}}
        gather_rows = self._items("get_gatherable_items")
        alter_rows = self._items("get_alterable_items")
        craft_rows = self._items("get_craftable_items")
        works = self._works()
        self._learn_facilities(works)
        material_cost = self._material_cost(gather_rows, alter_rows, craft_rows)
        stock = {}

        def owned(name):
            if name not in stock:
                stock[name] = self._owned(name)
            return stock[name]

        self._reconcile_productions(works, owned)
        needs, routes, expanded = {}, {}, {}
        # Resolve every relevant path before doing actions, including cycle checks.
        def route_for(name):
            if name in routes:
                return routes[name]
            gather = self._exact(gather_rows, name, command="get_gatherable_items")
            if gather is not None:
                route = {"kind": "gather", "recipe": name, "row": gather, "queued": 0, "requirements": {}}
            else:
                options = [self._exact(alter_rows, candidate, command="get_alterable_items", material_cost=material_cost)
                           for candidate in (name, *ALTERING_RECIPES.get(name, ()))]
                options = [candidate for candidate in options if candidate is not None]
                if options:
                    # Continue an already registered path when possible; otherwise
                    # choose ready input stock before a path requiring gathering.
                    options.sort(key=lambda row: (not any(work.get("DisplayName") == row["DisplayName"] for work in works),
                                                  row.get("Alterable") is not True,
                                                  row.get("Reason") != "not_enough_ingredient"))
                    row = options[0]
                    produced = self._validate_recipe(row, altering=True)
                    queued = 0
                    for option in options:
                        count = sum(work.get("DisplayName") == option["DisplayName"] for work in works)
                        entry = self.checkpoint.get("productions", {}).get(option["DisplayName"], {})
                        count += entry.get("unobserved", 0)
                        if count:
                            yields = [variant.get("ProducedPerWork") for variant in option.get("_catalog_variants", [option])]
                            amount = max((amount for amount in yields if positive(amount)), default=None)
                            if not positive(amount):
                                raise CraftingError(f"{option['DisplayName']}: 대기 중 생산량을 확인하지 못했습니다.")
                            queued += count * amount
                            self._track_work(name, option["DisplayName"], owned(name), needs.get(name, 0), amount)
                    route = {"kind": "alter", "recipe": row["DisplayName"], "row": row,
                             "produced": produced, "queued": queued,
                             "requirements": self._learn_requirements("get_alterable_items", row),
                             "options": [option["DisplayName"] for option in options],
                             "facility": self._facility(row["DisplayName"], row)}
                else:
                    row = self._exact(craft_rows, name, command="get_craftable_items", material_cost=material_cost)
                    if row is not None:
                        produced = self._validate_recipe(row)
                        route = {"kind": "craft", "recipe": name, "row": row, "produced": produced,
                                 "queued": 0, "requirements": self._learn_requirements("get_craftable_items", row)}
                    else:
                        route = {"kind": "manual", "recipe": name, "queued": 0, "requirements": {}}
            routes[name] = route
            return route

        def add_need(name, quantity, stack):
            needs[name] = needs.get(name, 0) + quantity
            if owned(name) >= needs[name]:
                return
            if name in stack or len(stack) >= 16:
                raise CraftingError(f"{name}: 재료 제작 경로가 순환하거나 너무 깊습니다.")
            route = route_for(name)
            if route["kind"] in ("gather", "manual"):
                return
            net = max(0, needs[name] - owned(name) - route["queued"])
            batches = math.ceil(net / route["produced"])
            extra = batches - expanded.get(name, 0)
            if extra <= 0:
                return
            expanded[name] = batches
            for ingredient, per_batch in route["requirements"].items():
                add_need(ingredient, per_batch * extra, (*stack, name))

        for name, quantity in final_needs.items():
            add_need(name, quantity, (self.recipe,))
        # Items that were sufficiently stocked during their first visit may
        # become production routes only after another branch adds a shared need.
        for name, route in routes.items():
            route["batches"] = expanded.get(name, 0)
        self._materials = {}
        for name, required in needs.items():
            route = routes.get(name, {})
            queued = route.get("queued", 0)
            matching = [work for work in works if work.get("DisplayName") in route.get("options", [])]
            count = len(matching) + sum(self.checkpoint.get("productions", {}).get(recipe, {}).get("unobserved", 0)
                                        for recipe in route.get("options", []))
            state = "준비 완료" if owned(name) >= required else (f"가공 {count}건 · {queued}개 생산 중" if queued else "준비 중")
            seconds = [work.get("RemainingSeconds") for work in matching
                       if work.get("State") == "InProgress" and type(work.get("RemainingSeconds")) in (int, float)
                       and work["RemainingSeconds"] >= 0]
            self._material(name, owned(name), required, state, min(seconds) if seconds else None)
            self._materials[name].update(queued=queued, queued_works=count)
        return {"final": final_row, "needs": needs, "routes": routes, "owned": stock,
                "works": works, "final_needs": final_needs}

    def _collect_ready_production(self, plan):
        relevant_recipes = set(self.checkpoint.get("productions", {}))
        facilities = set()
        for route in plan["routes"].values():
            if route["kind"] == "alter":
                relevant_recipes.update(route["options"])
                if route["facility"]:
                    facilities.add(route["facility"])
        for recipe in relevant_recipes:
            facility = self._facility(recipe)
            if facility:
                facilities.add(facility)
        for work in plan["works"]:
            if not self._completed(work):
                continue
            recipe, facility = work.get("DisplayName"), work.get("FacilityName")
            if recipe not in relevant_recipes and facility not in facilities:
                continue
            # Preserve registration evidence if a queue snapshot is stale. A
            # facility-wide receipt here could erase older rows before the new
            # confirmed-started row becomes visible, making counts ambiguous.
            if any(entry.get("unobserved") and (pending_recipe == recipe or self._facility(pending_recipe) == facility)
                   for pending_recipe, entry in self.checkpoint.get("productions", {}).items()):
                continue
            self._emit("collecting", f"{recipe} · 완료된 생산물 회수 중")
            result = self._action("complete_altering_work", recipe, ())
            if not positive(result.get("collected")):
                raise CraftingError(f"{recipe}: 생산물 회수를 확인하지 못했습니다. 자동 재수령하지 않습니다.")
            expected_products = set()
            for other in plan["works"]:
                same_facility = other.get("FacilityName") == facility or other.get("DisplayName") == recipe
                if same_facility and self._completed(other):
                    entry = self.checkpoint["productions"].get(other.get("DisplayName"))
                    if entry:
                        expected_products.add(entry["product"])
            for product in expected_products:
                if self._owned(product, after_action=True) <= plan["owned"].get(product, 0):
                    raise CraftingError(f"{product}: 회수 후 재료가 늘지 않아 중단했습니다. 자동 재수령하지 않습니다.")
            self.checkpoint["pending"] = None
            # Collection is facility-wide. Clear all completed tracked entries
            # from that facility, and re-observe still queued jobs next pass.
            for other in plan["works"]:
                if self._completed(other) and (other.get("FacilityName") == facility or other.get("DisplayName") == recipe):
                    self.checkpoint["productions"].pop(other.get("DisplayName"), None)
                    self._work_watch.pop(other.get("DisplayName"), None)
            self._sync_legacy_waiting()
            return True
        return False

    def _register_ready_production(self, plan):
        for product, route in plan["routes"].items():
            if route["kind"] != "alter" or route["batches"] <= 0 or not self._ready(route["row"], True):
                continue
            recipe, facility = route["recipe"], route["facility"]
            if self.checkpoint.get("productions", {}).get(recipe, {}).get("unobserved"):
                continue
            if facility:
                occupied = sum(work.get("FacilityName") == facility for work in plan["works"])
                occupied += sum(entry.get("unobserved", 0)
                                for pending_recipe, entry in self.checkpoint.get("productions", {}).items()
                                if self._facility(pending_recipe) == facility)
                if occupied >= QUEUE_CAPACITY:
                    continue
            self._emit("processing", f"{recipe} · 필요한 수량만 생산 시설에 등록 중")
            self._action("execute_altering", recipe, ("started",))
            self._track_work(product, recipe, plan["owned"][product], plan["needs"][product],
                             route["produced"], registered=True,
                             baseline_count=sum(work.get("DisplayName") == recipe for work in plan["works"]))
            self.checkpoint["pending"] = None
            return True
        return False

    def _craft_prepared(self, row, *, final):
        produced = self._validate_recipe(row)
        if not self._ready(row):
            raise CraftingError(f"{row['DisplayName']}: 제작 직전 재료 상태가 바뀌었습니다.")
        name = row["DisplayName"]
        automatic = row.get("_catalog_auto_choice") or self.checkpoint.get("variant_names", {}).get("get_craftable_items:" + name)
        if automatic and final:
            ready_yields = [variant.get("ProducedPerCraft") for variant in row.get("_catalog_variants", [row])
                            if self._ready(variant)]
            if any(positive(amount) and amount > self.remaining for amount in ready_yields):
                raise CraftingError(f"{name}: 같은 이름의 제작법 중 남은 목표 {self.remaining}개보다 많이 생산하는 방법이 있습니다. 목표 수량을 늘려주세요.")
        before = self._owned(name) if automatic else None
        self._emit("crafting", f"{name} · 재료 준비 완료, {produced}개 제작 중")
        result = self._action("execute_crafting", name, ("completed",), craftCount=1)
        if result.get("craftCount", 1) != 1:
            raise CraftingError(f"{name}: 실제 제작 횟수를 확인해주세요. 자동 재실행하지 않습니다.")
        if automatic:
            actual = self._owned(name, after_action=True) - before
            possible_yields = {variant.get("ProducedPerCraft") for variant in row.get("_catalog_variants", [row])
                               if positive(variant.get("ProducedPerCraft"))}
            if actual <= 0 or actual not in possible_yields:
                raise CraftingError(f"{name}: 동명 제작법 실행 후 실제 생산량을 확인하지 못했습니다. 자동 재실행하지 않습니다.")
            produced = actual
        if final:
            extra = max(0, produced - self.remaining)
            self.remaining = max(0, self.remaining - produced)
            self.checkpoint["completed"] = self.target - self.remaining
            if extra:
                self.checkpoint["extra_output"] = self.checkpoint.get("extra_output", 0) + extra
                self.status.emit(f"{name}: 게임에서 목표보다 {extra}개 더 생산했습니다. 추가 제작을 중단합니다.")
        self.checkpoint["pending"] = None
        self._emit("preparing" if self.remaining else "completed", f"{name} 제작 완료 · {self.target - self.remaining}/{self.target}")

    def _prepare_scheduled(self):
        """One caller, many in-game facilities: never wait ahead of useful work."""
        idle_started = None
        while self.remaining:
            self._check_stop()
            final_row = self._recipe("get_craftable_items", self.recipe)
            plan = self._plan_materials(final_row)
            if self._collect_ready_production(plan):
                idle_started = None
                continue
            if self._register_ready_production(plan):
                idle_started = None
                continue
            acted = False
            for product, route in plan["routes"].items():
                if route["kind"] == "craft" and route["batches"] > 0 and self._ready(route["row"]):
                    before = plan["owned"][product]
                    self._craft_prepared(route["row"], final=False)
                    if self._owned(product) <= before:
                        raise CraftingError(f"{product}: 작업 후 재료가 늘지 않아 중단했습니다.")
                    acted = True
                    break
            if acted:
                idle_started = None
                continue
            for product, route in plan["routes"].items():
                if route["kind"] != "gather" or plan["owned"][product] >= plan["needs"][product]:
                    continue
                if route["row"].get("ToolOk") is not True:
                    raise CraftingError(f"{product}: 채집 도구와 내구도를 확인해주세요.")
                before = plan["owned"][product]
                self._gather(product, before, plan["needs"][product])
                if self._owned(product) <= before:
                    raise CraftingError(f"{product}: 작업 후 재료가 늘지 않아 중단했습니다.")
                acted = True
                break
            if acted:
                idle_started = None
                continue
            if self._ready(final_row) and all(plan["owned"][name] >= quantity for name, quantity in plan["final_needs"].items()):
                self._craft_prepared(final_row, final=True)
                return
            for product, route in plan["routes"].items():
                if route["kind"] == "manual" and plan["owned"][product] < plan["needs"][product]:
                    raise CraftingError(f"{product}: 자동 채집·가공·제작 경로가 없습니다. 부족한 {plan['needs'][product] - plan['owned'][product]}개를 직접 준비해주세요.")
            has_pending = bool(self.checkpoint.get("productions"))
            relevant_facilities = {route.get("facility") for route in plan["routes"].values() if route["kind"] == "alter"}
            has_pending |= any(work.get("FacilityName") in relevant_facilities for work in plan["works"])
            if not has_pending:
                raise CraftingError(f"{self.recipe}: 재료 재고와 제작 가능 상태가 일치하지 않습니다. 창고·잠금을 확인해주세요.")
            if idle_started is None:
                idle_started = time.monotonic()
            if time.monotonic() - idle_started > self.MAX_WAIT_SECONDS:
                raise CraftingError("생산 시설 대기 시간을 초과했습니다. 대기열은 보존됩니다.")
            self._emit("processing", "필요한 채집·등록을 마쳤습니다 · 생산 완료를 기다리는 중")
            self._sleep(self.POLL_SECONDS)

    def _gather(self, name, before, required):
        self._material(name, before, required, "채집 중")
        self._emit("gathering", f"{name} 채집 중 · {before}/{required}")
        result = self._action("execute_gathering", name, ("completed", "started"))
        if result["result"] == "started":
            self.checkpoint["fishing"] = name
        self.checkpoint["pending"] = None
        if result["result"] == "started":
            deadline = time.monotonic() + 900
            try:
                while time.monotonic() < deadline:
                    owned = self._owned(name)
                    self._material(name, owned, required, "낚시 중")
                    self._emit("gathering", f"{name} 낚시 중 · {owned}/{required}")
                    if owned >= required:
                        return
                    self._sleep(self.POLL_SECONDS)
                raise CraftingError(f"{name}: 낚시 제한 시간에 도달했습니다.")
            finally:
                self._stop_fishing()

    def _stop_fishing(self):
        data = unpack(run_cli("stop_action", timeout=30))
        # The user may already have stopped fishing. The documented invalid_state
        # response means there is no stoppable action, so no fishing remains to
        # stop. Otherwise resume would stay blocked forever despite resolution.
        if isinstance(data, dict) and data.get("status") == "rejected" and (data.get("error") or data.get("reason")) == "invalid_state":
            self.checkpoint["fishing"] = None
            return
        if not isinstance(data, dict) or failure(data) or data.get("status") != "accepted":
            raise CraftingError("낚시 정지를 확인하지 못했습니다. 게임에서 낚시를 멈춰주세요.")
        self.checkpoint["fishing"] = None

    def _works(self):
        data = self._query("get_altering_works")
        if not isinstance(data, dict) or not isinstance(data.get("works"), list) or any(not isinstance(x, dict) for x in data["works"]):
            raise CraftingError("생산 시설 대기열을 확인하지 못했습니다.")
        return data["works"]

    def _wait_altering(self, waiting):
        """Legacy single-job wait helper. The active scheduler never calls it."""
        product, recipe = waiting["product"], waiting["recipe"]
        started = changed = time.monotonic()
        previous_signature = None
        while time.monotonic() - started < self.MAX_WAIT_SECONDS:
            self._check_stop()
            owned = self._owned(product)
            works = [x for x in self._works() if x.get("DisplayName") == recipe]
            if not works:
                if owned > waiting["before"]:
                    self.checkpoint["waiting"] = None
                    return
                raise CraftingError(f"{recipe}: 등록했던 생산 작업과 생산물을 찾지 못했습니다. 시설을 확인해주세요.")
            completed = [x for x in works if x.get("IsCompleted") is True or x.get("State") == "Completed"]
            if completed:
                self._emit("collecting", f"{recipe} · 완료된 생산물 회수 중")
                result = self._action("complete_altering_work", completed[0]["DisplayName"], ())
                if not positive(result.get("collected")):
                    raise CraftingError(f"{recipe}: 생산물 회수를 확인하지 못했습니다. 자동 재수령하지 않습니다.")
                self.checkpoint["pending"] = None
                self.checkpoint["waiting"] = None
                return
            queued_only = all(x.get("State") == "NotStarted" for x in works)
            seconds = [x.get("RemainingSeconds") for x in works]
            seconds = [x for x in seconds if isinstance(x, (int, float)) and x >= 0]
            remaining = min(seconds) if seconds and not queued_only else None
            signature = tuple((x.get("State"), x.get("RemainingSeconds")) for x in works)
            if signature != previous_signature:
                changed, previous_signature = time.monotonic(), signature
            elif not queued_only and time.monotonic() - changed > self.NO_PROGRESS_SECONDS:
                raise CraftingError(f"{recipe}: 생산 진행 정보가 갱신되지 않습니다. 시설을 확인해주세요.")
            # A queued job can legitimately remain unchanged behind another
            # long facility job. The overall wait cap still bounds this state.
            state = "가공 대기" if queued_only else "가공 중"
            self._material(product, owned, waiting["required"], state, remaining)
            self._emit("processing", f"{recipe} {state}" + (f" · {int(remaining)}초 남음" if remaining is not None else " · 시설 작업 대기"))
            self._sleep(self.POLL_SECONDS)
        raise CraftingError(f"{recipe}: 생산 대기 시간을 초과했습니다. 대기열은 보존됩니다.")

    def run(self):
        try:
            cp, completed = self.checkpoint, self.checkpoint.get("completed", 0)
            if cp.get("recipe") != self.recipe or cp.get("target") != self.target or type(completed) is not int or not 0 <= completed <= self.target:
                raise CraftingError("저장된 작업 진행 정보가 현재 제작 목표와 다릅니다.")
            self.remaining = self.target - completed
            if cp.get("fishing"):
                self._stop_fishing()
            if cp.get("pending"):
                raise CraftingError(f"{cp['pending'].get('name', self.recipe)}: 직전 동작 결과가 미확인 상태입니다. 중복 제작을 막기 위해 자동 재실행하지 않습니다.")
            self._migrate_production_checkpoint()
            while self.remaining:
                self._check_stop()
                self._materials = {}
                self._prepare_scheduled()
            self._emit("completed", f"{self.recipe} · 목표 {self.target}개 제작 완료")
        except _Paused:
            self._emit("paused", "일시정지 · 완료한 제작과 생산 대기열을 보존했습니다.")
        except Exception as exc:
            self._emit("blocked", str(exc))
            self.blocked.emit(str(exc))
        finally:
            self.stopped.emit()
