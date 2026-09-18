"""Popup shown when the app can't reach the game via MabinogiMobile_CLI.exe - walks the
user through turning the AI Connector on in-game, with the two reference screenshots."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

ASSETS_DIR = Path(__file__).parent
IMAGE_PATHS = [ASSETS_DIR / "AI_CONNECTOR_ON_1.png", ASSETS_DIR / "AI_CONNECTOR_ON_2.png"]


class ConnectorGuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("게임 연결 안내")
        self.setModal(False)

        layout = QVBoxLayout(self)

        message = QLabel(
            "마비노기 모바일과 연결할 수 없습니다.<br><br>"
            "1. 마비노기 모바일(PC 버전)을 실행하세요.<br>"
            "2. [메뉴(≡)] → [환경설정] → [게임] → <b>AI 제어 → 마비노기 모바일 AI 커넥터</b>를 켜세요.<br>"
            "3. 아래 오른쪽 상단의 스위치를 다시 켜서 연결을 시도해보세요."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        images_row = QHBoxLayout()
        for path in IMAGE_PATHS:
            image_label = QLabel()
            if path.exists():
                pixmap = QPixmap(str(path)).scaledToWidth(220, Qt.SmoothTransformation)
                image_label.setPixmap(pixmap)
            images_row.addWidget(image_label)
        layout.addLayout(images_row)

        close_btn = QPushButton("확인")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
