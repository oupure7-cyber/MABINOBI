"""Keep the requested item list visible; refresh actual recipes from the game."""
import json
from collections import defaultdict
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from ..cli_client import run_cli
from .crafting_engine import unpack, failure
from .recipe_variants import distinct_recipe_variants, choose_recipe_variant


def reference_recipes():
    """Screenshot names/yields are browsing defaults, never crafting ingredients."""
    path = Path(__file__).parent / 'assets' / 'crafting_items_reference.json'
    items = json.loads(path.read_text(encoding='utf-8'))['items']
    result = {}
    for index, item in enumerate(items):
        row = {'DisplayName': item['name'], '_catalog_reference_only': True,
               '_catalog_group': item['group'], '_catalog_order': index}
        produced = item.get('visible_produced_per_craft')
        if type(produced) is int and produced > 0:
            row['ProducedPerCraft'] = produced
        result[item['name']] = row
    return result


def merge_reference_recipes(live):
    """A failed/missing recipe never removes the user's requested item names.

    Unique spacing/case matches only associate screenshot labels with live rows.
    Actual workers still receive the exact DisplayName returned by the game.
    """
    rows = {name: dict(row) for name, row in live.items()}
    normalized = defaultdict(list)
    for name in live:
        normalized[''.join(name.split()).casefold()].append(name)
    for name, reference in reference_recipes().items():
        matches = normalized.get(''.join(name.split()).casefold(), [])
        key = name if name in rows else matches[0] if len(matches) == 1 else None
        if key is not None:
            rows[key]['_catalog_group'] = reference['_catalog_group']
            rows[key]['_catalog_order'] = reference['_catalog_order']
        else:
            reference['_catalog_not_in_live'] = True
            rows[name] = reference
    return rows


def catalogue_sort_key(pair):
    name, row = pair
    return row.get('_catalog_order', 10000), name

def parse_recipes(data):
    data = unpack(data)
    if failure(data):
        raise ValueError('게임 연결을 확인한 뒤 제작 목록을 다시 불러와주세요.')
    if isinstance(data, list): data = {'items': data}
    if isinstance(data, dict) and data.get('craftingUnlocked') is False:
        raise ValueError('게임의 제작 기능을 먼저 해금해주세요.')
    if not isinstance(data, dict) or not isinstance(data.get('items'), list):
        raise ValueError('게임에 접속하고 AI 커넥터를 켜주세요.')
    grouped = defaultdict(list)
    for row in data['items']:
        if not isinstance(row, dict):
            raise ValueError('제작 목록 응답이 올바르지 않습니다. 다시 불러와주세요.')
        name = row.get('DisplayName')
        if isinstance(name, str) and name.strip():
            grouped[name].append(dict(row))
    result = {}
    for name, entries in grouped.items():
        variants = distinct_recipe_variants(entries)
        # Preserve a useful representative while retaining all game variants.
        # The worker compares them again using the requested output quantity.
        row = dict(choose_recipe_variant(variants) or variants[0])
        row['_catalog_variant_count'] = len(variants)
        row['_catalog_variants'] = variants
        result[name] = row
    return result

class RecipeCatalogWorker(QThread):
    result = Signal(object)
    def run(self):
        self.result.emit(run_cli('get_craftable_items', timeout=30))

REASONS = {'not_enough_ingredient':'재료 준비 필요', 'ingredient_locked':'재료 잠금',
           'insufficient_living_skill_level':'생활 스킬 부족', 'insufficient_facility_level':'시설 레벨 부족',
           'insufficient_decor_score':'데코 점수 부족', 'insufficient_transfer_cost':'이동 비용 부족'}

def recipe_state(row):
    if row.get('_catalog_reference_only'):
        return '현재 게임 목록에 없음' if row.get('_catalog_not_in_live') else '제작 조건 확인 전'
    if row.get('_catalog_variant_count', 1) > 1:
        return f"동명 제작법 {row['_catalog_variant_count']}종 · 자동 선택"
    if row.get('Craftable'): return '제작 가능'
    return REASONS.get(row.get('Reason'), '조건 확인 필요')
