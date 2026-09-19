"""Cook from live connector recipes, without guessing ingredient quantities."""
import json
import time
from PySide6.QtCore import QThread, Signal
from ..cli_client import run_cli

RECIPES = ('호박 수프', '가든 샐러드', '녹차 크레이프 케이크', '매콤 파프리카 스튜',
           '카레라이스', '농어 매운탕', '토마토 생선 크림 커넬', '풍미 가득 스테이크',
           '파이크퍼치 필레 리소토')

class CookingError(Exception): pass

class RecipeCookingWorker(QThread):
    status = Signal(str)
    blocked = Signal(str)
    stopped = Signal()

    def __init__(self, recipe, target):
        super().__init__()
        self.recipe = recipe
        self.remaining = target
        self.cancelled = False
        self._max_craft_per_call: int | None = None  # learned from a facility's invalid_count reply

    def request_stop(self): self.cancelled = True

    def call(self, command, body=None, timeout=30):
        if self.cancelled: raise CookingError('사용자가 중지했습니다.')
        data = run_cli(command, body, timeout=timeout)
        if isinstance(data, dict) and (data.get('error') or data.get('pipe') == 'disconnected' or data.get('status', 'accepted') != 'accepted'):
            raise CookingError(str(data.get('kind') or data.get('message') or data.get('error') or data.get('reason') or data.get('status')))
        return data

    def items(self, command):
        data = self.call(command)
        items = data if isinstance(data, list) else data.get('items') if isinstance(data, dict) else None
        if not isinstance(items, list): raise CookingError(command + ': 목록을 확인하지 못했습니다.')
        return items

    def recipe_info(self, name):
        items = self.items('get_craftable_items')
        exact = [r for r in items if r.get('DisplayName') == name]
        matches = exact or [r for r in items if ''.join(r.get('DisplayName', '').split()).casefold() == ''.join(name.split()).casefold()]
        if len(matches) != 1: raise CookingError(f'{name}: 레시피가 없거나 이름을 확정할 수 없습니다. 해금 상태를 확인해주세요.')
        return matches[0]

    def owned(self, name):
        items = self.call('get_items', json.dumps({'name': name}, ensure_ascii=False))
        if not isinstance(items, list): raise CookingError(name + ': 보유량 조회 실패')
        return sum(x.get('Count', 0) for x in items if x.get('DisplayName') == name and not x.get('IsLocked'))

    def ensure(self, name, needed, stack):
        if name in stack or len(stack) > 8: raise CookingError(name + ': 재료 제작 순환을 확인해주세요.')
        before = self.owned(name)
        if before >= needed: return
        gather = next((x for x in self.items('get_gatherable_items') if x.get('DisplayName') == name), None)
        if gather:
            if not gather.get('ToolOk'): raise CookingError(name + ': 채집 도구 또는 내구도를 확인해주세요.')
            while before < needed:
                self.status.emit(f'{name} 준비 중 · {before}/{needed}')
                result = self.call('execute_gathering', json.dumps({'displayName': name}, ensure_ascii=False), 900)
                if not isinstance(result, dict): raise CookingError(name + ': 채집 결과 확인 실패')
                if result.get('result') == 'started':
                    # Fishing returns immediately and must be stopped explicitly.
                    deadline = time.monotonic() + 900
                    try:
                        while not self.cancelled and time.monotonic() < deadline:
                            if self.owned(name) >= needed: break
                            for _ in range(10):
                                if self.cancelled: break
                                self.msleep(500)
                        else: raise CookingError(name + ': 낚시 제한 시간 도달 또는 중지')
                    finally:
                        stop = run_cli('stop_action', timeout=30)
                        if not isinstance(stop, dict) or stop.get('status') != 'accepted':
                            raise CookingError('낚시 정지를 확인하지 못했습니다. 게임 화면을 확인해주세요.')
                elif result.get('result') != 'completed':
                    raise CookingError(name + ': 채집이 완료되지 않았습니다.')
                after = self.owned(name)
                if after <= before: raise CookingError(name + ': 재료가 늘지 않아 중단했습니다.')
                before = after
            return
        # Some ingredients are themselves craftable. Unsupported shop/altering
        # ingredients stop with an explicit message instead of looping.
        while self.owned(name) < needed:
            previous = self.owned(name)
            self.craft_one(name, stack)
            if self.owned(name) <= previous: raise CookingError(name + ': 직접 준비가 필요한 재료입니다.')

    def craft_one(self, name, stack=()):
        for _ in range(30):
            recipe = self.recipe_info(name)
            produced = recipe.get('ProducedPerCraft')
            if not isinstance(produced, int) or produced <= 0: raise CookingError(name + ': 1회 생산량 확인 실패')
            if recipe.get('Craftable'):
                self.status.emit(f'{name} 제작 중 · 1회 {produced}개')
                result = self.call('execute_crafting', json.dumps({'displayName': recipe['DisplayName'], 'craftCount': 1}, ensure_ascii=False), 900)
                if not isinstance(result, dict) or result.get('result') != 'completed':
                    raise CookingError(name + ': 제작 완료를 확인하지 못했습니다. 재개 전 결과를 확인해주세요.')
                return produced
            if recipe.get('Reason') != 'not_enough_ingredient':
                raise CookingError(f"{name}: {recipe.get('Reason', '제작 조건 확인 필요')}")
            missing = recipe.get('MissingIngredients')
            if not missing: raise CookingError(name + ': 부족한 재료 정보가 없습니다.')
            for ing in missing:
                if not isinstance(ing.get('Required'), int) or ing['Required'] <= 0 or not ing.get('DisplayName'):
                    raise CookingError(name + ': 재료 정보 확인 실패')
                self.ensure(ing['DisplayName'], ing['Required'], (*stack, name))
        raise CookingError(name + ': 재료 확인 횟수를 초과했습니다.')

    def craft_batch(self, name, count, stack=()):
        """Craft up to `count` more of `name`, requesting as many repetitions per
        execute_crafting call as the facility allows instead of always craftCount=1 -
        each call costs 정령의 날개 regardless of craftCount, so N separate 1-unit calls
        waste (N-1) calls' worth versus one batched call (user request, 2026-09-20).
        Learns the real per-call cap from invalid_count+maxCount the same way
        food_crafting_job.py already does, since it's facility-specific and not
        knowable up front.

        If `name` is this worker's own target (self.recipe), self.remaining is
        decremented after every individual call - not just once at the end - so a
        failure partway through a multi-call batch still keeps credit for whatever
        already succeeded.
        """
        for _ in range(30):
            if count <= 0: return
            recipe = self.recipe_info(name)
            produced = recipe.get('ProducedPerCraft')
            if not isinstance(produced, int) or produced <= 0: raise CookingError(name + ': 1회 생산량 확인 실패')
            if not recipe.get('Craftable'):
                if recipe.get('Reason') != 'not_enough_ingredient':
                    raise CookingError(f"{name}: {recipe.get('Reason', '제작 조건 확인 필요')}")
                missing = recipe.get('MissingIngredients')
                if not missing: raise CookingError(name + ': 부족한 재료 정보가 없습니다.')
                for ing in missing:
                    if not isinstance(ing.get('Required'), int) or ing['Required'] <= 0 or not ing.get('DisplayName'):
                        raise CookingError(name + ': 재료 정보 확인 실패')
                    self.ensure(ing['DisplayName'], ing['Required'], (*stack, name))
                continue
            want = max(1, count // produced)
            if self._max_craft_per_call is not None:
                want = min(want, self._max_craft_per_call)
            self.status.emit(f'{name} 제작 중 · {want}회 x {produced}개')
            if self.cancelled: raise CookingError('사용자가 중지했습니다.')
            data = run_cli('execute_crafting', json.dumps({'displayName': recipe['DisplayName'], 'craftCount': want}, ensure_ascii=False), timeout=900)
            max_count = data.get('maxCount') if isinstance(data, dict) else None
            if isinstance(data, dict) and data.get('error') == 'invalid_count' and isinstance(max_count, int) and 0 < max_count < want:
                # facility caps a single call lower than we asked for - learn the real
                # cap and retry immediately in smaller chunks from here on.
                self._max_craft_per_call = max_count
                continue
            if isinstance(data, dict) and (data.get('error') or data.get('pipe') == 'disconnected' or data.get('status', 'accepted') != 'accepted'):
                raise CookingError(str(data.get('kind') or data.get('message') or data.get('error') or data.get('reason') or data.get('status')))
            if not isinstance(data, dict) or data.get('result') != 'completed':
                raise CookingError(name + ': 제작 완료를 확인하지 못했습니다. 재개 전 결과를 확인해주세요.')
            got = want * produced
            count -= got
            if name == self.recipe:
                self.remaining = max(0, self.remaining - got)
        raise CookingError(name + ': 재료 확인 횟수를 초과했습니다.')

    def run(self):
        try:
            if self.remaining > 0:
                self.status.emit(f'{self.recipe} · 목표 {self.remaining}개')
                self.craft_batch(self.recipe, self.remaining)
            self.status.emit(f'✅ {self.recipe} 제작 완료')
        except Exception as exc:
            self.blocked.emit(str(exc))
        finally:
            self.stopped.emit()
