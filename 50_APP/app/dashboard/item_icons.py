"""Exact-name icons sourced from the public mabimobi.life market.

No fuzzy matching or invented fallback icons. Manifest records source URLs.
"""
import json
from functools import lru_cache
from pathlib import Path
from PySide6.QtGui import QIcon

ICON_DIR = Path(__file__).parent / 'assets' / 'item_icons'

@lru_cache(maxsize=1)
def _manifest():
    return json.loads((ICON_DIR / 'manifest.json').read_text(encoding='utf-8'))

def item_icon(name: str) -> QIcon:
    try:
        entry = _manifest().get(name)
        if entry and entry.get('name') == name:
            path = ICON_DIR / Path(entry['file']).name
            if path.is_file(): return QIcon(str(path))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return QIcon()

def spec_item_name(spec) -> str:
    if spec.key.startswith('equipment_'): return spec.key[len('equipment_'):]
    if spec.key.startswith('cooking_'): return spec.key[len('cooking_'):].rsplit('_', 1)[0]
    if spec.key.startswith('gather_'): return spec.key[len('gather_'):]
    if spec.key.startswith('veggie_stir_fry_'): return '야채볶음'
    # Group operations are not individual items in the market.
    return spec.name
