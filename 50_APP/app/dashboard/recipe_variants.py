"""Compare and rank same-name connector recipe records deterministically.

The connector executes by display name. Selection identifies the preferred
preparation plan; the caller must still verify the operation's actual output.
Unknown connector fields remain part of identity and all alternatives are kept.
"""
from __future__ import annotations

import json
import copy
import math
from collections.abc import Callable


def recipe_signature(row: dict) -> str:
    """Canonical response data; only app-owned catalogue metadata is omitted.

    Shortage order does not change a recipe. Every shortage field (including
    Required and Owned) is kept, as are identifiers and all other recipe fields.
    Other lists retain their order because their semantics are not known here.
    """
    payload = {key: value for key, value in row.items()
               if not key.startswith("_catalog_")}
    missing = payload.get("MissingIngredients")
    if isinstance(missing, list):
        payload["MissingIngredients"] = sorted(
            missing,
            key=lambda ingredient: json.dumps(ingredient, ensure_ascii=False,
                                              sort_keys=True, separators=(",", ":")),
        )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def distinct_recipe_variants(rows: list[dict]) -> list[dict]:
    """Return first representatives of distinct records, without altering them."""
    found, signatures = [], set()
    for row in rows:
        signature = recipe_signature(row)
        if signature not in signatures:
            signatures.add(signature)
            found.append(row)
    return found


def _positive_integer(value):
    return type(value) is int and value > 0


def _variant_score(row, desired, material_cost):
    """Lower is better; invalid rows never outrank a structurally valid row."""
    malformed = not isinstance(row.get("DisplayName"), str) or not row.get("DisplayName")
    if "Craftable" in row:
        ready_key, output_key = "Craftable", "ProducedPerCraft"
    elif "Alterable" in row:
        ready_key, output_key = "Alterable", "ProducedPerWork"
    elif "ToolOk" in row:
        ready_key, output_key = "ToolOk", None
    else:
        ready_key, output_key = None, None
        malformed = True
    if ready_key and type(row[ready_key]) is not bool:
        malformed = True
    produced = row.get(output_key) if output_key else 1
    if not _positive_integer(produced):
        malformed = True
        produced = 1
    missing = row.get("MissingIngredients", [])
    if not isinstance(missing, list):
        malformed = True
        missing = []
    deficits = {}
    for ingredient in missing:
        if not isinstance(ingredient, dict):
            malformed = True
            continue
        name, required, owned = ingredient.get("DisplayName"), ingredient.get("Required"), ingredient.get("Owned", 0)
        if (not isinstance(name, str) or not name or not _positive_integer(required)
                or type(owned) is not int or owned < 0):
            malformed = True
            continue
        # Repeated representations of the same shortage are not additive.
        deficits[name] = max(deficits.get(name, 0), max(0, required - owned))
    ready = bool(ready_key and row.get(ready_key) is True)
    shortage = not ready and row.get("Reason") == "not_enough_ingredient" and any(deficits.values())
    if not ready and row.get("Reason") == "not_enough_ingredient" and not any(deficits.values()):
        malformed = True
    readiness = 0 if ready else 1 if shortage else 2
    total_cost, obtainable = 0.0, True
    # A ready recipe has no preparation cost even if a connector includes stale
    # shortage metadata. Do not invoke material lookup needlessly for it.
    if not ready:
        for name, deficit in sorted(deficits.items()):
            if not deficit:
                continue
            try:
                cost = material_cost(name, deficit) if material_cost else deficit
                cost = float(cost)
            except (TypeError, ValueError, OverflowError, RuntimeError, LookupError):
                cost = math.inf
            if not math.isfinite(cost) or cost < 0:
                obtainable = False
                total_cost = math.inf
            else:
                total_cost += cost
    exact_target = not _positive_integer(desired) or desired % produced == 0
    return (bool(malformed), readiness, not obtainable, not exact_target,
            total_cost / produced, recipe_signature(row))


def choose_recipe_variant(
    rows: list[dict], *, desired: int | None = None,
    material_cost: Callable[[str, int], float] | None = None,
) -> dict | None:
    """Choose the most useful live preparation option without losing variants.

    Ready recipes outrank shortages; actionable shortages outrank hard locks.
    For shortages, obtainable inputs outrank missing acquisition routes, followed
    by a yield that divides the desired target and the least preparation cost
    per produced item. The cost callback takes (ingredient name, missing count).
    Without it, each missing unit costs one. A stable canonical signature breaks
    ties, so connector list order cannot change the selection.

    Same-name alternatives do not cause an error. Metadata retains every distinct
    record for callers to check actual yields/conditions after name-only execution.
    Input records are never mutated, including their nested shortage dictionaries.
    """
    usable = [row for row in rows if isinstance(row, dict)]
    if not usable:
        return None
    variants = sorted(distinct_recipe_variants(usable), key=recipe_signature)
    selected = min(variants, key=lambda row: _variant_score(row, desired, material_cost))
    clean = lambda row: {key: copy.deepcopy(value) for key, value in row.items()
                         if not key.startswith("_catalog_")}
    result = clean(selected)
    result.update(_catalog_variant_count=len(variants),
                  _catalog_variants=[clean(row) for row in variants],
                  _catalog_selected_signature=recipe_signature(selected))
    return result
