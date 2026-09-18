"""Helpers for opening URLs and spawning visible terminal windows for interactive steps
(npm install, `claude` login) that a background subprocess call can't handle."""

import os
import subprocess

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def open_terminal(command: str, cwd: str | None = None) -> None:
    """Open a new visible cmd.exe window running `command` and leave it open (/k)."""
    if os.name != "nt":
        return
    subprocess.Popen(
        f'start "" cmd /k {command}',
        shell=True,
        cwd=cwd,
    )
