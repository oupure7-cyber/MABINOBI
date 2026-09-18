"""Double-click launcher for 마비노비 (50_APP/main.py) - distribution build.

Kept deliberately dependency-free (stdlib only, no PySide6/project imports) so PyInstaller
only has to bundle a tiny stub - the real app still runs via the system Python + its
already-installed packages, this just makes sure that Python + those packages actually exist
before handing off to 50_APP/main.py, installing whatever's missing first. That also means it
keeps working after 50_APP changes, without rebuilding the exe.

What "일반 사용자도 exe 하나로 바로 쓸 수 있게" (2026-09-19) means here concretely: a fresh
Windows machine with nothing but this exe and the AI_Mabinogi folder should still end up with
마비노비 running, by:
  1. finding a real python.exe (skipping the Microsoft Store alias stub that resolves but does
     nothing) - if none exists, offering to install one via winget automatically;
  2. checking 50_APP/requirements.txt's packages (PySide6) import cleanly - if not, running
     `pip install -r` for the user;
  3. only then launching 50_APP/main.py.

The exe itself is windowed (no console) for the common case where everything's already
installed - launch is instant and silent, same as before. A console is only allocated
on-demand (AllocConsole) when there's actually first-run setup work to show progress for, so
the user isn't left staring at a frozen, unresponsive window while pip/winget run.

What this launcher deliberately does NOT install: the 마비노기 모바일 게임 client itself, or
turning on its AI 커넥터 옵션- those are the user's own game installation and a menu toggle
in-game (40_ONBOARDING/01_사용자_설치_가이드.md 6단계), not something a launcher can do for
them. 50_APP's own connector_guide.py already detects a missing game connection at that point
and shows instructions once the GUI starts.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import time
import webbrowser
import winreg
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
MB_ICONERROR = 0x10
MB_ICONINFORMATION = 0x40
MB_YESNO = 0x04
MB_ICONQUESTION = 0x20
IDYES = 6

_console_allocated = False


def app_root() -> Path:
    """Project root (the folder containing 50_APP/) - the frozen exe's own directory when
    built (그게 마비노비.exe가 놓이는 곳), else one level up from this file's own location
    when run unfrozen for local testing (this file lives in launcher/, the project root is
    its parent)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


# -- user-facing messages ----------------------------------------------------------------


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, "마비노비", MB_ICONERROR)


def show_info(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, "마비노비", MB_ICONINFORMATION)


def ask_yes_no(message: str) -> bool:
    result = ctypes.windll.user32.MessageBoxW(0, message, "마비노비", MB_YESNO | MB_ICONQUESTION)
    return result == IDYES


def ensure_console() -> None:
    """Attach a real console the first time there's actual setup work to narrate - most
    launches never call this at all (everything's already installed), so they stay instant
    and silent exactly like before."""
    global _console_allocated
    if _console_allocated:
        return
    ctypes.windll.kernel32.AllocConsole()
    ctypes.windll.kernel32.SetConsoleTitleW("마비노비 - 최초 실행 준비 중")
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    _console_allocated = True


def log(message: str) -> None:
    if _console_allocated:
        print(message, flush=True)


# -- PATH handling -------------------------------------------------------------------------


def refresh_path_from_registry() -> None:
    """winget/pip installs update the registry's PATH, not this already-running process's
    os.environ - re-read both the machine and user PATH values (same fix used manually
    throughout this project's own dev session) so a freshly-installed python.exe is actually
    findable without asking the user to re-launch."""
    parts: list[str] = []
    for hive, subkey in (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                parts.append(value)
        except OSError:
            continue
    if parts:
        os.environ["PATH"] = os.pathsep.join(parts) + os.pathsep + os.environ.get("PATH", "")


# -- python discovery ------------------------------------------------------------------------


def candidate_pythons() -> list[str]:
    """Real python.exe candidates, most reliable first - skips the Microsoft Store alias stub
    (resolves and prints a version banner but runs nothing when no real Python is installed)."""
    candidates: list[str] = []
    seen: set[str] = set()

    def add(exe: str) -> None:
        norm = os.path.normcase(exe)
        if os.path.isfile(exe) and norm not in seen:
            seen.add(norm)
            candidates.append(exe)

    # A project-local virtualenv (.venv, if someone's set one up next to the project) wins
    # over whatever's on PATH - keeps a dev's own pinned environment authoritative.
    add(str(app_root() / ".venv" / "Scripts" / "python.exe"))

    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        exe = os.path.join(directory, "python.exe")
        if "WindowsApps" in exe:
            continue
        add(exe)

    # Fallback: the python.org/winget default per-user install location, in case PATH hasn't
    # picked it up yet even after a registry refresh.
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        programs = Path(local_appdata) / "Programs" / "Python"
        if programs.is_dir():
            for entry in sorted(programs.glob("Python3*"), reverse=True):
                add(str(entry / "python.exe"))

    return candidates


def resolve_python() -> str | None:
    for exe in candidate_pythons():
        try:
            result = subprocess.run(
                [exe, "--version"], capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and "Python" in (result.stdout + result.stderr):
            return exe
    return None


def install_python_via_winget() -> str | None:
    winget = shutil.which("winget")
    if not winget:
        show_info(
            "Python이 설치되어 있지 않고, 이 PC에는 winget(자동 설치 도구)도 없습니다.\n"
            "python.org 다운로드 페이지를 열어드릴게요 - 설치 시 'Add python.exe to PATH'를 꼭 체크해주세요.\n"
            "설치가 끝나면 마비노비를 다시 실행해주세요."
        )
        webbrowser.open("https://www.python.org/downloads/")
        return None

    if not ask_yes_no(
        "마비노비를 실행하려면 Python이 필요한데, 이 PC엔 설치되어 있지 않습니다.\n"
        "지금 자동으로 설치할까요? (인터넷 연결 필요, 1~2분 정도 걸려요)"
    ):
        return None

    ensure_console()
    log("Python 설치 중... (winget)")
    try:
        subprocess.run(
            [
                winget,
                "install",
                "--id",
                "Python.Python.3.12",
                "-e",
                "--source",
                "winget",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ],
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"설치 중 오류: {exc}")
        return None

    refresh_path_from_registry()
    python_exe = resolve_python()
    if python_exe is None:
        log("설치는 됐지만 python.exe를 아직 못 찾았습니다. PC를 재시작한 뒤 다시 실행해주세요.")
    return python_exe


# -- package check/install -------------------------------------------------------------------


def requirements_satisfied(python_exe: str, requirements: Path) -> bool:
    packages = []
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        # "PySide6>=6.11" -> "PySide6" (import-name check only needs the package name)
        name = line.split(">=")[0].split("==")[0].split("<")[0].strip()
        if name:
            packages.append(name)

    for name in packages:
        try:
            result = subprocess.run(
                [python_exe, "-c", f"import {name}"],
                capture_output=True,
                timeout=30,
                creationflags=CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode != 0:
            return False
    return True


def install_requirements(python_exe: str, requirements: Path) -> bool:
    ensure_console()
    log(f"필요한 패키지를 설치합니다 ({requirements.name}). 몇 분 걸릴 수 있어요...\n")
    try:
        result = subprocess.run([python_exe, "-m", "pip", "install", "-r", str(requirements)], timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log(f"설치 중 오류: {exc}")
        return False
    return result.returncode == 0


# -- main ------------------------------------------------------------------------------------


def main() -> None:
    # PyInstaller's onefile bootloader narrows the frozen process's DLL search path to its own
    # bundle dir; that's inherited by the system python.exe we spawn below and can break ITS
    # own DLL loading (python3xx.dll, Qt, ...) if left in place. Reset it before we do anything
    # else (friend's fix, found independently while testing on a machine where this mattered).
    if getattr(sys, "frozen", False) and os.name == "nt":
        ctypes.windll.kernel32.SetDllDirectoryW(None)

    root = app_root()
    main_py = root / "50_APP" / "main.py"
    requirements = root / "50_APP" / "requirements.txt"

    if not main_py.exists():
        show_error(f"{main_py} 를 찾을 수 없습니다.\n이 실행 파일은 AI_Mabinogi 폴더 안에 있어야 합니다.")
        return

    python_exe = resolve_python()

    if python_exe is None:
        python_exe = install_python_via_winget()
        if python_exe is None:
            if _console_allocated:
                log("\nPython을 준비하지 못해 마비노비를 실행할 수 없습니다.")
                time.sleep(3)
            return

    if requirements.exists() and not requirements_satisfied(python_exe, requirements):
        if not install_requirements(python_exe, requirements):
            show_error(
                "필요한 패키지 설치에 실패했습니다.\n"
                "인터넷 연결을 확인하고 다시 실행해주세요. 계속 실패하면 다음 명령을 직접 실행해보세요:\n"
                f'"{python_exe}" -m pip install -r "{requirements}"'
            )
            if _console_allocated:
                time.sleep(3)
            return
        log("\n설치 완료! 마비노비를 실행합니다...")
        time.sleep(1)

    process = subprocess.Popen([python_exe, str(main_py)], cwd=str(root), creationflags=CREATE_NO_WINDOW)

    # Quick crash check - if 50_APP/main.py dies almost immediately (e.g. an import error our
    # checks above didn't catch), say so instead of just silently doing nothing.
    time.sleep(2)
    if process.poll() is not None:
        show_error(
            "마비노비 실행 중 오류가 발생한 것 같습니다 (바로 종료됨).\n"
            f'터미널에서 직접 실행해서 오류 내용을 확인해보세요:\n"{python_exe}" "{main_py}"'
        )


if __name__ == "__main__":
    main()
