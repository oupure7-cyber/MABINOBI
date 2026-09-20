"""First-run (and every-run) check that MabinogiMobile_CLI.exe can actually be found.

This app assumes the Nexon default (C:\\Nexon\\MabinogiMobile\\MabinogiMobile_CLI.exe),
but not every install lives there. If it's missing, this asks the user to locate their
install folder once via a folder picker and remembers the choice (app/cli_settings.py)
so it never asks again - unless that saved path stops working too (game moved/
reinstalled elsewhere), in which case it asks again automatically.
"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from .. import cli_settings
from ..cli_client import CLI_EXE_NAME, cli_path, set_cli_path


def ensure_cli_path(project_root: Path, parent=None) -> None:
    if os.environ.get("MABINOGI_CLI_PATH"):
        return  # explicit developer override - never second-guess it with a popup

    saved = cli_settings.load_cli_path(project_root)
    if saved:
        set_cli_path(saved)

    if Path(cli_path()).is_file():
        return

    QMessageBox.information(
        parent, "마비노기 설치 위치를 찾을 수 없음",
        f"{cli_path()}\n위 경로에서 {CLI_EXE_NAME}를 찾지 못했습니다.\n"
        "마비노기 모바일이 설치된 폴더를 직접 선택해주세요.",
    )
    while True:
        folder = QFileDialog.getExistingDirectory(parent, "마비노기 모바일 설치 폴더 선택")
        if not folder:
            return  # cancelled - app proceeds and degrades gracefully, same as before
        candidate = Path(folder) / CLI_EXE_NAME
        if candidate.is_file():
            set_cli_path(str(candidate))
            cli_settings.save_cli_path(project_root, str(candidate))
            return
        retry = QMessageBox.question(
            parent, "찾지 못함",
            f"선택한 폴더에서 {CLI_EXE_NAME}를 찾지 못했습니다. 다시 선택할까요?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if retry != QMessageBox.Yes:
            return
