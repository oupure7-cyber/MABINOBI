"""MCP server that wraps Nexon's official MabinogiMobile_CLI.exe (the AI Connector CLI).

Command catalog and body shapes are taken verbatim from `MabinogiMobile_CLI.exe capabilities`,
recorded in ../10_RESEARCH/02_cli_capabilities_raw.json. All 28 documented commands are mapped
1:1 below; none of them cover marketplace/cash-shop/guild-management/auto-leveling, so no extra
scope filtering is implemented here (see ../00_SPEC/02_scope_boundaries.md). If a future game
update adds new capabilities, re-check that file before wiring them up here.
"""

import json
import os
import subprocess

from mcp.server.mcpserver import MCPServer

CLI_PATH = os.environ.get(
    "MABINOGI_CLI_PATH",
    r"C:\Nexon\MabinogiMobile\MabinogiMobile_CLI.exe",
)

mcp = MCPServer("mabinogi-ai-connector")


def _run_cli(command: str, body: str | None = None, timeout: int = 180) -> dict:
    """Invoke MabinogiMobile_CLI.exe <command> [body] and parse its JSON stdout.

    Never raises for expected failure modes (missing exe, timeout, non-JSON output,
    non-zero exit) - those come back as an {"error": ...} dict so they surface as a
    normal tool result instead of an MCP-level error.
    """
    args = [CLI_PATH, command]
    if body is not None:
        args.append(body)

    try:
        result = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", timeout=timeout
        )
    except FileNotFoundError:
        return {"error": "cli_not_found", "message": f"CLI not found at {CLI_PATH}"}
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "message": f"{command} did not respond within {timeout}s"}

    stdout = result.stdout.strip()
    if not stdout:
        return {
            "error": "empty_response",
            "message": result.stderr.strip() or "CLI produced no output (is the game running?)",
        }

    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"error": "invalid_json", "message": "CLI output was not valid JSON", "raw": stdout}


# ---- no-body queries -------------------------------------------------------

@mcp.tool()
def capabilities() -> dict:
    """List the AI Connector's available commands. If loading=true the catalog isn't
    ready yet - re-query after the user has entered the game."""
    return _run_cli("capabilities")


@mcp.tool()
def get_current_environment() -> dict:
    """Query current location / weather / Erinn time / housing state."""
    return _run_cli("get_current_environment")


@mcp.tool()
def get_activity() -> dict:
    """Query current auto-play / travel / combat / dialogue / instrument / interaction state."""
    return _run_cli("get_activity")


@mcp.tool()
def get_my_info() -> dict:
    """Query my character's title, stats, combat/living/decor scores, and current vitals
    (HP, satiety, inventory weight, active buff count)."""
    return _run_cli("get_my_info")


@mcp.tool()
def get_quests() -> dict:
    """List currently visible/executable Quest Tracker entries with objectives and progress."""
    return _run_cli("get_quests")


@mcp.tool()
def get_currencies() -> dict:
    """Query my main currency balances (includes 정령의 날개)."""
    return _run_cli("get_currencies")


@mcp.tool()
def get_near_npcs() -> dict:
    """List nearby talkable NPCs (search radius 30)."""
    return _run_cli("get_near_npcs")


@mcp.tool()
def get_near_pcs() -> dict:
    """List nearby players (search radius 30)."""
    return _run_cli("get_near_pcs")


@mcp.tool()
def get_inventory() -> dict:
    """Query current/max inventory weight. For the item list use get_items."""
    return _run_cli("get_inventory")


@mcp.tool()
def get_daily_missions() -> dict:
    """List active daily missions with goal, progress, and completion state."""
    return _run_cli("get_daily_missions")


@mcp.tool()
def get_weekly_missions() -> dict:
    """List active weekly missions with goal, progress, and completion state."""
    return _run_cli("get_weekly_missions")


@mcp.tool()
def get_altering_works() -> dict:
    """Query in-progress and completed altering (가공) works with remaining time."""
    return _run_cli("get_altering_works")


@mcp.tool()
def stop_action() -> dict:
    """Stop the current stoppable action (instrument performance, sitting, auto-play,
    carrying, gathering). Rejects with invalid_state if nothing stoppable is in progress."""
    return _run_cli("stop_action")


@mcp.tool()
def stand_up() -> dict:
    """Stand up from sitting. Rejects with not_sitting if not currently sitting."""
    return _run_cli("stand_up")


# ---- raw-string body (optional filter or required text) -------------------

@mcp.tool()
def write_chat(message: str) -> dict:
    """Send a chat message, or execute a behavior/facial command exactly as listed in
    get_social_actions. Max 50 chars. Requires the user's in-game confirmation before
    it is actually sent - it is NEVER sent silently. May be rejected with rate_limited
    (wait retryAfterSeconds) or unsupported_command (reserved '/'.'#' commands)."""
    return _run_cli("write_chat", message)


@mcp.tool()
def get_music_scores(filter: str = "") -> dict:
    """List owned music scores (inventory/account/character storage). Optional
    case-insensitive substring filter on title; empty returns everything."""
    return _run_cli("get_music_scores", filter if filter else None)


@mcp.tool()
def get_instruments(filter: str = "") -> dict:
    """List owned instruments with durability and equipped state. Optional
    case-insensitive substring filter on name; empty returns everything."""
    return _run_cli("get_instruments", filter if filter else None)


@mcp.tool()
def get_gatherable_items(filter: str = "") -> dict:
    """List gatherable items whose living-skill level requirement is already met, with
    tool availability (ToolOk). Optional case-insensitive substring filter; empty
    returns everything."""
    return _run_cli("get_gatherable_items", filter if filter else None)


@mcp.tool()
def get_alterable_items(filter: str = "") -> dict:
    """List altering (가공) recipes with alterability and missing ingredients. Optional
    case-insensitive substring filter on recipe or ingredient name; empty returns
    everything."""
    return _run_cli("get_alterable_items", filter if filter else None)


@mcp.tool()
def get_craftable_items(filter: str = "") -> dict:
    """List crafting recipes with craftability and missing ingredients. Optional
    case-insensitive substring filter on recipe or ingredient name; empty returns
    everything."""
    return _run_cli("get_craftable_items", filter if filter else None)


@mcp.tool()
def get_social_actions(filter: str = "") -> dict:
    """List available behaviors (with their ChatCommands) and facials (with their
    EmojiText). Execute one by sending its ChatCommands/EmojiText via write_chat.
    Optional case-insensitive substring filter; empty returns everything."""
    return _run_cli("get_social_actions", filter if filter else None)


# ---- JSON body --------------------------------------------------------------

@mcp.tool()
def get_items(category: str = "", name: str = "") -> dict:
    """List owned consumable-category items (foods, materials, gathered items, etc;
    not equipment/costume/pet), with counts and location. Both filters are optional,
    case-insensitive substrings; omit both for the full list."""
    body: dict = {}
    if category:
        body["category"] = category
    if name:
        body["name"] = name
    return _run_cli("get_items", json.dumps(body) if body else None)


@mcp.tool()
def play_music_score(title: str) -> dict:
    """Start playing a music score. title must exactly match a DisplayTitle from
    get_music_scores. Requires an equipped instrument (see change_instrument) -
    rejected with no_instrument otherwise."""
    return _run_cli("play_music_score", json.dumps({"title": title}))


@mcp.tool()
def change_instrument(name: str) -> dict:
    """Equip an owned instrument. name must exactly match a Name from get_instruments.
    Rejected with is_playing_instrument while playing, or level_requirement if the
    level is not enough."""
    return _run_cli("change_instrument", json.dumps({"name": name}))


@mcp.tool()
def execute_gathering(display_name: str) -> dict:
    """Gather a named item (from get_gatherable_items) until its target quantity, or
    start auto fishing for a fishing-only item. One call gathers up to 100; call again
    for more. Auto fishing has no target - end it with stop_action.
    Costs 5 정령의 날개 per call; rejected with not_enough_currency if the balance is
    too low. If a blocking UI/state appears, it stops and returns blocked with a kind
    describing what the user must resolve - do not try to click through it."""
    return _run_cli("execute_gathering", json.dumps({"displayName": display_name}))


@mcp.tool()
def execute_altering(display_name: str) -> dict:
    """Queue a named altering (가공) recipe from get_alterable_items, including travel
    to its facility. Asynchronous/queue-based - check get_altering_works for progress,
    then collect with complete_altering_work.
    Costs 5 정령의 날개 per call. If a blocking UI/state appears, it stops and returns
    blocked with a kind describing what the user must resolve."""
    return _run_cli("execute_altering", json.dumps({"displayName": display_name}))


@mcp.tool()
def complete_altering_work(display_name: str) -> dict:
    """Collect all completed altering works at the ONE facility that makes the named
    item (from get_altering_works), including travel to it. Rejected with
    not_completed_yet if that item itself is still in progress."""
    return _run_cli("complete_altering_work", json.dumps({"displayName": display_name}))


@mcp.tool()
def execute_crafting(display_name: str, craft_count: int = 1) -> dict:
    """Craft a named recipe from get_craftable_items, including travel to its facility
    and result collection. craft_count is the NUMBER OF CRAFTS (each craft yields
    ProducedPerCraft items from get_craftable_items), not the output item count; has a
    per-facility upper limit (rejected as invalid_count with maxCount if exceeded).
    Costs 5 정령의 날개 per call. If a blocking UI/state appears, it stops and returns
    blocked with a kind describing what the user must resolve."""
    return _run_cli(
        "execute_crafting", json.dumps({"displayName": display_name, "craftCount": craft_count})
    )


if __name__ == "__main__":
    mcp.run()
