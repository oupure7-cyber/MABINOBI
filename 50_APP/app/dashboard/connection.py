"""Background worker so the game-connection check (subprocess call, up to a few seconds)
doesn't freeze the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..cli_client import status


class ConnectionCheckWorker(QThread):
    result = Signal(bool, str)

    def run(self) -> None:
        response = status()
        ok = response.get("pipe") == "connected"
        detail = "connected" if ok else response.get("message", str(response))
        self.result.emit(ok, detail)
