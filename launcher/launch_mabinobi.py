"""Double-click launcher for 마비노비 (50_APP/main.py).

Kept deliberately dependency-free (no PySide6/project imports) so PyInstaller only has to
bundle a tiny stub - the real app still runs via the system Python + its already-installed
packages, this just finds that Python and starts 50_APP/main.py with the right working
directory. That also means it keeps working after 50_APP changes, without rebuilding the exe.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path


def app_root() -> Path:
    """Directory this launcher lives in - the frozen exe's own path when built, else this
    file's own path when run as a plain script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_python() -> str | None:
    """Same WindowsApps-stub-skipping search as app/onboarding/checks.py's resolve_python."""
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        exe = os.path.join(directory, "python.exe")
        if "WindowsApps" in exe:
            continue
        if os.path.isfile(exe):
            return exe
    return None


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, "마비노비", 0x10)  # MB_ICONERROR


def main() -> None:
    root = app_root()
    main_py = root / "50_APP" / "main.py"
    if not main_py.exists():
        show_error(f"{main_py} 를 찾을 수 없습니다.\n이 실행 파일은 AI_Mabinogi 폴더 안에 있어야 합니다.")
        return

    python_exe = find_python()
    if python_exe is None:
        show_error(
            "Python을 찾지 못했습니다.\n"
            "40_ONBOARDING/01_사용자_설치_가이드.md 를 참고해 Python을 설치한 뒤 다시 실행해주세요."
        )
        return

    subprocess.Popen(
        [python_exe, str(main_py)],
        cwd=str(root),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


if __name__ == "__main__":
    main()
