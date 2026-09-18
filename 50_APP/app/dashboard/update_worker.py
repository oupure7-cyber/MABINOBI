"""Background worker for app/updater.py - runs the GitHub check + download off the UI
thread so a slow/dead network never freezes the dashboard on launch. Silent by design:
on "no update"/any error it emits nothing at all, same as the rest of the update flow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..updater import check_for_update, download_asset


class UpdateCheckWorker(QThread):
    update_ready = Signal(str, str)  # (downloaded_exe_path, version)

    def __init__(self, current_exe: Path, current_version: str, parent=None):
        super().__init__(parent)
        self._current_exe = current_exe
        self._current_version = current_version

    def run(self) -> None:
        info = check_for_update(self._current_version)
        if info is None:
            return
        dest = self._current_exe.parent / f"{self._current_exe.stem}.update.exe"
        if download_asset(info["download_url"], dest):
            self.update_ready.emit(str(dest), info["version"])
