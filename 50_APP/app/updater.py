"""Silent self-update via GitHub Releases (2026-09-19). Stdlib only - no PySide6/project
imports here - same "keep it dependency-free" rule launcher/launch_mabinobi.py used to
follow, since every extra import here adds to every single launch of the frozen exe.

User requirement: end users should never see or need to know about GitHub - no popup
asking permission, no visible URL. So every function here fails silently (returns None /
False) on any error - no internet, no releases published yet, rate-limited, whatever -
never raises out to the caller. The dashboard just gets "nothing happened" in that case.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

GITHUB_REPO = "oupure7-cyber/MABINOBI"
# ASCII on purpose - confirmed empirically (2026-09-19, first real release) that GitHub
# silently rejects non-ASCII release asset filenames: uploading with a Korean name became
# "default.exe" server-side, and renaming it to Korean afterward was silently a no-op,
# while renaming to an ASCII name worked instantly. This is purely a GitHub-side asset
# identifier though - it never touches the local file's actual name. The exe on a user's
# disk stays whatever they named it (마비노비.exe); apply_update_and_relaunch() derives the
# downloaded file's local name from the *running* exe's own name, never from this constant.
ASSET_NAME = "MabiNobi.exe"
_TIMEOUT = 10

# Bridge/redirect mechanism (2026-09-19, built ahead of ever needing it - see CHANGELOG).
# The problem it solves: every already-installed exe has GITHUB_REPO/ASSET_NAME baked into
# its own compiled code, so it can only ever look in the one place it was built to look.
# If the app/asset is ever renamed or moved to a different repo, old installs would just
# silently stop finding updates forever - there's no way to reach out and patch code that's
# already running on someone else's PC.
#
# The fix: before trusting a release as "the real latest", check whether it carries a
# REDIRECT_ASSET_NAME asset instead. If it does, that release isn't a real version at all -
# it's a pointer ({"repo": "...", "asset_name": "..."}) telling every client (new AND old,
# since this redirect-following code ships in every build from now on) where to actually
# look next. So migrating the app's identity later needs no special "bridge build" at the
# old location at all - just publish one release there whose only content is this pointer.
REDIRECT_ASSET_NAME = "redirect.json"
MAX_REDIRECT_HOPS = 3


def _parse_version(text: str) -> Optional[tuple[int, ...]]:
    text = text.strip().lstrip("vV")
    if not text:
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


def _fetch_latest_release(repo: str) -> Optional[dict]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MabiNobi-Updater", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def _fetch_redirect(assets: list[dict]) -> Optional[dict]:
    """If this release is a bridge/redirect marker, return its {"repo", "asset_name"}
    payload - else None (the overwhelmingly common case: a normal release)."""
    marker = next((a for a in assets if a.get("name") == REDIRECT_ASSET_NAME), None)
    url = marker.get("browser_download_url") if marker else None
    if not url:
        return None
    request = urllib.request.Request(url, headers={"User-Agent": "MabiNobi-Updater"})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not payload.get("repo"):
        return None
    return payload


def check_for_update(current_version: str) -> Optional[dict]:
    """None if already up to date (or offline / no releases yet / any hiccup), else
    {"version": "1.2.3", "download_url": "..."} for the newest published (non-draft,
    non-prerelease) release with a matching exe asset attached. Transparently follows
    up to MAX_REDIRECT_HOPS bridge/redirect markers (see REDIRECT_ASSET_NAME above) before
    giving up - a real migration would only ever need one hop, the cap is just a safety
    net against a misconfigured or circular redirect chain."""
    repo, asset_name = GITHUB_REPO, ASSET_NAME

    for _ in range(MAX_REDIRECT_HOPS):
        release = _fetch_latest_release(repo)
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            return None
        assets = release.get("assets", [])

        redirect = _fetch_redirect(assets)
        if redirect:
            repo = redirect.get("repo", repo)
            asset_name = redirect.get("asset_name", asset_name)
            continue

        latest = _parse_version(release.get("tag_name", ""))
        current = _parse_version(current_version)
        if latest is None or current is None or latest <= current:
            return None

        asset = next((a for a in assets if a.get("name") == asset_name), None)
        download_url = asset.get("browser_download_url") if asset else None
        if not download_url:
            return None

        return {"version": release.get("tag_name", "").strip().lstrip("vV"), "download_url": download_url}

    return None


def download_asset(url: str, dest: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "MabiNobi-Updater"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        dest.write_bytes(data)
        return dest.exists() and dest.stat().st_size > 0
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def apply_update_and_relaunch(new_exe: Path, current_exe: Path) -> None:
    """Spawns a detached, hidden PowerShell helper that waits until nothing still has
    `current_exe` open, swaps the downloaded exe into place, and relaunches it - then
    returns immediately. Caller must quit the Qt app right after calling this; the swap
    itself happens after the caller's process is gone.

    Waits by *exe path*, not by a single PID: PyInstaller's onefile bootloader on Windows
    actually runs as two processes (an outer bootloader that stays alive and an inner one
    that's the real running app, `os.getpid()` only sees the inner one) and both keep the
    same exe file open - confirmed empirically via `Get-CimInstance Win32_Process` showing
    a parent/child pair sharing one image path. Waiting for that path to have zero owners
    covers both, and works the same even if PyInstaller ever changes that internal model.

    PowerShell (not cmd/.bat): the exe's own filename is Korean (마비노비.exe), and
    cmd.exe's batch-file codepage handling mangles non-ASCII paths; PowerShell reads a
    UTF-8-BOM script correctly without any chcp dance.
    """
    script = f"""
$exePath = "{current_exe}"
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {{
    $stillRunning = Get-Process | Where-Object {{ $_.Path -eq $exePath }} | Select-Object -First 1
    if (-not $stillRunning) {{ break }}
    Start-Sleep -Milliseconds 500
}}
for ($i = 0; $i -lt 10; $i++) {{
    try {{
        Move-Item -Force -LiteralPath "{new_exe}" -Destination "{current_exe}" -ErrorAction Stop
        break
    }} catch {{
        Start-Sleep -Milliseconds 500
    }}
}}
Start-Process -FilePath "{current_exe}"
Remove-Item -LiteralPath "$PSCommandPath" -Force -ErrorAction SilentlyContinue
"""
    script_path = Path(tempfile.gettempdir()) / "mabinobi_update.ps1"
    script_path.write_text(script, encoding="utf-8-sig")
    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden", "-File", str(script_path),
        ],
        # CREATE_BREAKAWAY_FROM_JOB: if this app is ever itself running inside a Windows
        # Job Object that kills all children when the job closes (sandboxes, some process
        # supervisors), the helper must survive past this process exiting - that's the
        # whole point of it. Confirmed via a real end-to-end test that without this flag,
        # a job-object-wrapped parent can silently kill the "detached" helper mid-script.
        creationflags=(
            subprocess.CREATE_NO_WINDOW
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_BREAKAWAY_FROM_JOB
        ),
        close_fds=True,
    )
