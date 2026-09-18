"""'사용 가이드' popup: renders 10_RESEARCH/03_cli_command_reference_*.md (the CLI command
table) as read-only rich text. Picks the most recently dated file so re-checking the
reference after a game patch (see that doc's own note) just means dropping in a new
dated file - no code change needed here."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QTextBrowser, QVBoxLayout

REFERENCE_GLOB = "03_cli_command_reference_*.md"


def find_latest_reference(project_root: Path) -> Path | None:
    candidates = sorted((project_root / "10_RESEARCH").glob(REFERENCE_GLOB))
    return candidates[-1] if candidates else None


class GuideDialog(QDialog):
    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("사용 가이드")
        self.resize(900, 750)

        layout = QVBoxLayout(self)

        doc_path = find_latest_reference(project_root)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        if doc_path is not None:
            browser.setMarkdown(doc_path.read_text(encoding="utf-8"))
        else:
            browser.setPlainText(
                f"{project_root / '10_RESEARCH'} 안에 {REFERENCE_GLOB} 파일이 없습니다."
            )
        layout.addWidget(browser)

        if doc_path is not None:
            layout.addWidget(QLabel(f"출처: {doc_path.relative_to(project_root)}"))

        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
