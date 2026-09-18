"""Direct wrapper around Nexon's MabinogiMobile_CLI.exe.

This app calls the CLI directly - the dashboard doesn't need Claude Code/MCP running to
show character info, it only needs the game client + this CLI (see
10_RESEARCH/01_ai_connector_interface.md).
"""

import json
import os
import subprocess

DEFAULT_CLI_PATH = r"C:\Nexon\MabinogiMobile\MabinogiMobile_CLI.exe"


def cli_path() -> str:
    return os.environ.get("MABINOGI_CLI_PATH", DEFAULT_CLI_PATH)


def run_cli(command: str, body: str | None = None, timeout: int = 180) -> dict:
    """Invoke MabinogiMobile_CLI.exe <command> [body] and parse its JSON stdout.

    Never raises for expected failure modes - those come back as {"error": ...}.
    """
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


def status() -> dict:
    """Quick connectivity check: {"pipe": "connected"} when the game client is reachable."""
    return run_cli("status", timeout=10)
