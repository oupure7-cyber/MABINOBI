"""One-shot '채집 한 번' JOB worker (added 2026-09-18, replacing the always-visible 채집
바로가기 button grid that used to live in gather_panel.py - see that module's docstring).

Each JOB just calls execute_gathering once for a fixed display name (up to 100 per call,
matching the game's own per-call cap) and finishes - there's no internal repeat loop, since
running it more than once is exactly what the JOB queue's own `◀ N ▶` stepper is for, same as
every other JOB type in this app. GATHER_ITEMS is the same user-picked list (2026-09-18,
duplicates collapsed, 가나다순) the button grid used to render.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QThread, Signal

from ..cli_client import run_cli
from .widgets import classify_cli_result

GATHER_TIMEOUT = 900  # execute_gathering can take several minutes for a full 100-item run

GATHER_ITEMS = sorted(
    dict.fromkeys(
        [
            "황금 개암 버섯",
            "황금 달걀",
            "황금 거미줄",
            "황금 네잎클로버",
            "황금 우유",
            "황금 사과",
            "황금 나뭇가지",
            "황금 헤이즐넛",
            "황금 거미줄+",
            "단단한 통나무",
            "황금 풍뎅이",
            "부드러운 통나무",
            "벼락 맞은 나뭇가지",
            "황금 부스러기",
            "마력 깃든 돌",
            "반짝이는 이끼",
            "황금 이끼",
            "황금 양털",
            "두꺼운 양털",
            "황금 양털+",
            "황금 줄기",
            "묵직한 감자",
            "황금 나비",
            "황금 잠자리",
            "황금 사슴벌레",
        ]
    )
)


class GatherJobWorker(QThread):
    status = Signal(str)
    blocked = Signal(str)
    stopped = Signal()

    def __init__(self, display_name: str, parent=None):
        super().__init__(parent)
        self._display_name = display_name

    def request_stop(self) -> None:
        # A single execute_gathering call can't be interrupted mid-flight once started (same
        # limitation every other worker in this app has for its blocking CLI calls) - dragging
        # this JOB to the trash while it's running still lets the in-flight call finish first.
        pass

    def run(self) -> None:
        name = self._display_name
        self.status.emit(f"⏳ '{name}' 채집 중... (약 2분 소요, 최대 15분, 최대 100개)")
        body = json.dumps({"displayName": name}, ensure_ascii=False)
        data = run_cli("execute_gathering", body, timeout=GATHER_TIMEOUT)
        ok, reason = classify_cli_result(data)
        if ok:
            gained = data.get("gained") if isinstance(data, dict) else None
            self.status.emit(f"✅ '{name}' 채집 완료{f' ({gained}개)' if gained else ''}")
        else:
            kind = data.get("kind") if isinstance(data, dict) else None
            if kind:
                self.blocked.emit(str(kind))
            else:
                self.status.emit(f"⚠️ '{name}' 채집 실패: {reason}")
        self.stopped.emit()
