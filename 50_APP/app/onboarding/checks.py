"""Environment checks used by the onboarding wizard.

Each check is a plain function returning (ok: bool, detail: str) so wizard pages can
show the result directly without needing to know how the check was done. Nothing here
is hardcoded to a specific user's machine - PATH is searched at runtime so the same
build works for whoever installs it (see 40_ONBOARDING/01_사용자_설치_가이드.md).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from ..cli_client import run_cli

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _run(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def check_node() -> tuple[bool, str]:
    exe = shutil.which("node")
    if not exe:
        return False, "node를 찾을 수 없음 (PATH에 없음)"
    result = _run([exe, "--version"])
    if result and result.returncode == 0:
        return True, f"{result.stdout.strip()} ({exe})"
    return False, "node가 설치되어 있지만 실행에 실패함"


def check_claude_code() -> tuple[bool, str]:
    exe = shutil.which("claude")
    if not exe:
        return False, "claude를 찾을 수 없음 (PATH에 없음)"
    result = _run([exe, "--version"])
    if result and result.returncode == 0:
        return True, f"{result.stdout.strip()} ({exe})"
    return False, "claude가 설치되어 있지만 실행에 실패함"


def candidate_pythons() -> list[list[str]]:
    """Python interpreters worth trying, most reliable first.

    Skips the Microsoft Store "python.exe" alias stub, which resolves and prints a
    version banner but exits without actually running anything when no real Python
    is installed.
    """
    candidates: list[list[str]] = []
    seen: set[str] = set()

    py_launcher = shutil.which("py")
    if py_launcher:
        candidates.append([py_launcher, "-3"])

    for d in os.environ.get("PATH", "").split(os.pathsep):
        exe = os.path.join(d, "python.exe") if d else ""
        if not exe or "WindowsApps" in exe:
            continue
        norm = os.path.normcase(exe)
        if os.path.isfile(exe) and norm not in seen:
            seen.add(norm)
            candidates.append([exe])

    return candidates


def resolve_python() -> list[str] | None:
    for cand in candidate_pythons():
        result = _run(cand + ["--version"])
        if result and result.returncode == 0 and "Python" in (result.stdout + result.stderr):
            return cand
    return None


def check_python() -> tuple[bool, str]:
    cmd = resolve_python()
    if not cmd:
        return False, "실행 가능한 Python을 찾을 수 없음"
    result = _run(cmd + ["--version"])
    return True, f"{result.stdout.strip() or result.stderr.strip()} ({' '.join(cmd)})"


def check_mcp_package() -> tuple[bool, str]:
    cmd = resolve_python()
    if not cmd:
        return False, "Python을 먼저 설치해야 함"
    result = _run(cmd + ["-c", "import mcp; print(getattr(mcp, '__version__', 'unknown'))"], timeout=15)
    if result and result.returncode == 0:
        return True, f"mcp 패키지 설치됨 (v{result.stdout.strip()})"
    return False, "mcp 패키지가 설치되어 있지 않음 (pip install -r 30_MCP_SERVER/requirements.txt 필요)"


def install_mcp_package(project_root: Path) -> tuple[bool, str]:
    cmd = resolve_python()
    if not cmd:
        return False, "Python을 먼저 설치해야 함"
    req = project_root / "30_MCP_SERVER" / "requirements.txt"
    result = _run(cmd + ["-m", "pip", "install", "-r", str(req)], timeout=180)
    if result and result.returncode == 0:
        return True, "설치 완료"
    message = (result.stderr.strip() if result else "실행 실패")[-500:]
    return False, message or "설치 실패"


def mcp_json_status(project_root: Path) -> tuple[bool, str]:
    mcp_json = project_root / ".mcp.json"
    if not mcp_json.exists():
        return False, ".mcp.json이 프로젝트 루트에 없음"
    try:
        data = json.loads(mcp_json.read_text(encoding="utf-8"))
        configured = data["mcpServers"]["mabinogi-ai-connector"]["command"]
    except (json.JSONDecodeError, KeyError, OSError):
        return False, ".mcp.json 형식이 예상과 다름"

    if not os.path.isfile(configured):
        return False, f"등록된 Python 경로가 이 PC에 없음: {configured}"
    return True, f"등록된 Python: {configured}"


def write_mcp_json(project_root: Path) -> tuple[bool, str]:
    """Point .mcp.json's server command at this machine's resolved Python interpreter."""
    cmd = resolve_python()
    if not cmd:
        return False, "Python을 먼저 설치해야 함"
    if len(cmd) > 1:
        # .mcp.json's "command" is a single executable; `py -3` needs its arg folded in.
        return False, "python.exe 단독 설치가 필요함 (py 런처만으로는 자동 설정 불가, 수동으로 .mcp.json 수정 필요)"

    mcp_json = project_root / ".mcp.json"
    data = {
        "mcpServers": {
            "mabinogi-ai-connector": {
                "command": cmd[0],
                "args": ["30_MCP_SERVER/server.py"],
            }
        }
    }
    try:
        mcp_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError as exc:
        return False, f"쓰기 실패: {exc}"
    return True, f"{mcp_json}에 {cmd[0]} 등록 완료"


def check_game_connector() -> tuple[bool, str]:
    response = run_cli("status", timeout=10)
    if response.get("pipe") == "connected":
        return True, "게임과 연결됨 (AI 커넥터 활성화 상태)"
    if "error" in response:
        return False, response.get("message", response["error"])
    return False, f"연결되지 않음: {response}"
