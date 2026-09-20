"""Direct wrapper around Nexon's MabinogiMobile_CLI.exe.

This app calls the CLI directly - the dashboard doesn't need Claude Code/MCP running to
show character info, it only needs the game client + this CLI (see
10_RESEARCH/01_ai_connector_interface.md).
"""

import json
import os
import subprocess
import threading

CLI_EXE_NAME = "MabinogiMobile_CLI.exe"
DEFAULT_CLI_PATH = rf"C:\Nexon\MabinogiMobile\{CLI_EXE_NAME}"

# The game's CLI exe does not tolerate two concurrent invocations (confirmed by hand:
# two workers hitting it at once corrupts/breaks both calls). Every caller so far has
# avoided this only by convention (checking each other's busy flags before starting a
# worker) - this lock makes that guarantee real instead of relying on every future
# caller remembering to check. Existing callers already only ever call sequentially in
# practice, so wrapping run_cli() in it changes nothing for them.
_CLI_LOCK = threading.Lock()

# Set (once, at startup) by app/dashboard/cli_setup.py when the default install path
# doesn't exist and the user picked their real one instead. Not every player installed
# to the Nexon default folder.
_custom_cli_path: str | None = None


def set_cli_path(path: str) -> None:
    global _custom_cli_path
    _custom_cli_path = path


def cli_path() -> str:
    # An explicit env var always wins - it's a deliberate developer override (e.g. for
    # testing the cli_not_found path itself) and must never be second-guessed by the
    # auto-detected/saved path.
    return os.environ.get("MABINOGI_CLI_PATH") or _custom_cli_path or DEFAULT_CLI_PATH


def _invoke(command: str, body: str | None, timeout: int) -> dict:
    args = [cli_path(), command]
    if body is not None:
        args.append(body)

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except FileNotFoundError:
        return {"error": "cli_not_found", "message": f"CLI not found at {cli_path()}"}
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


def run_cli(command: str, body: str | None = None, timeout: int = 180) -> dict:
    """Invoke MabinogiMobile_CLI.exe <command> [body] and parse its JSON stdout.

    Never raises for expected failure modes - those come back as {"error": ...}.
    Blocks until any other in-flight run_cli/try_run_cli call finishes.
    """
    with _CLI_LOCK:
        return _invoke(command, body, timeout)


def try_run_cli(command: str, body: str | None = None, timeout: int = 180) -> dict | None:
    """Like run_cli, but returns None immediately (never calls the CLI) if it's busy.

    For opportunistic background polling (e.g. character-switch detection) that must
    never stall waiting behind a long-running job action, and must never itself delay
    one.
    """
    if not _CLI_LOCK.acquire(blocking=False):
        return None
    try:
        return _invoke(command, body, timeout)
    finally:
        _CLI_LOCK.release()


def status() -> dict:
    """Quick connectivity check: {"pipe": "connected"} when the game client is reachable."""
    return run_cli("status", timeout=10)
