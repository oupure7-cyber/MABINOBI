"""Persists a user-picked MabinogiMobile_CLI.exe path across restarts *and* future
auto-updates (see app/dashboard/cli_setup.py for the detection/prompt flow itself).

Stored in PROJECT_ROOT (same place as character_data/), not inside the exe - the
auto-updater (app/updater.py) only ever swaps the exe file itself via Move-Item, never
touching sibling files/folders, so this survives every update exactly like
character_data/ already does.
"""
from __future__ import annotations

import json
from pathlib import Path

SETTINGS_FILE_NAME = "cli_settings.json"


def _settings_path(project_root: Path) -> Path:
    return Path(project_root) / SETTINGS_FILE_NAME


def load_cli_path(project_root: Path) -> str | None:
    path = _settings_path(project_root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data.get("cli_path") if isinstance(data, dict) else None


def save_cli_path(project_root: Path, cli_path: str) -> None:
    _settings_path(project_root).write_text(
        json.dumps({"cli_path": cli_path}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
