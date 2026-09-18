"""Bottom-half center panel: a Spotify-ish music player built on get_music_scores/
play_music_score/stop_action/get_activity. The game has no native "queue" concept - one
play_music_score call plays exactly one score - so the queue here is purely a UI construct:
we hold an ordered list client-side and advance it ourselves by polling get_activity for
Performance.IsPlaying going False.

Left: search box + full score catalog (drag source, read-only).
Right: now-playing label + queue (drag-reorderable, accepts drops from the catalog) + a
trash drop zone that removes whatever queue item was just dragged onto it.
"""

from __future__ import annotations

import json

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..cli_client import run_cli
from .widgets import classify_cli_result

POLL_INTERVAL_MS = 4000


class SongCatalogList(QListWidget):
    """Left-side full score list - drag source only, never accepts drops itself."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)


class QueueListWidget(QListWidget):
    """Right-side play queue - reorderable in place, accepts drops from the catalog.
    Remembers whichever item it last started dragging so a TrashZone elsewhere can remove
    that exact item (not just "the first one with a matching title")."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self._drag_item: QListWidgetItem | None = None

    def startDrag(self, supported_actions) -> None:  # noqa: N802 - Qt override
        self._drag_item = self.currentItem()
        super().startDrag(supported_actions)

    def take_dragged_item(self) -> QListWidgetItem | None:
        item = self._drag_item
        self._drag_item = None
        return item


class TrashZone(QLabel):
    """Drop a queue item here to delete it. Only accepts drags that came from the queue
    itself (dragging a catalog song here does nothing - there's nothing to delete yet)."""

    def __init__(self, queue: QueueListWidget, parent=None):
        super().__init__("🗑", parent)
        self._queue = queue
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedWidth(48)
        self.setStyleSheet(
            "QLabel { background-color: #2b2b30; border: 2px dashed #555; border-radius: 8px;"
            " font-size: 20px; }"
        )

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.source() is self._queue:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        item = self._queue.take_dragged_item()
        if item is not None:
            row = self._queue.row(item)
            if row >= 0:
                self._queue.takeItem(row)
        event.acceptProposedAction()


class InstrumentBar(QWidget):
    """Horizontal row of owned-instrument buttons below the player. Clicking one calls
    change_instrument; the equipped one is shown checked."""

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 0)

        title = QLabel("악기 변경")
        title.setStyleSheet("color: #aaa; font-size: 11px;")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setFixedHeight(56)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        host = QWidget()
        self._row = QHBoxLayout(host)
        self._row.setContentsMargins(4, 4, 4, 4)
        self._row.setSpacing(6)
        scroll.setWidget(host)
        outer.addWidget(scroll)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #999; font-size: 11px;")
        outer.addWidget(self._status)

    def refresh(self) -> None:
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        data = run_cli("get_instruments")
        if not isinstance(data, list):
            self._row.addWidget(QLabel("⚠️ 악기 목록을 불러오지 못했습니다."))
            self._row.addStretch(1)
            return

        for entry in data:
            name = entry.get("Name", "")
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(bool(entry.get("IsEquipped", False)))
            btn.clicked.connect(lambda _checked=False, n=name: self._change_instrument(n))
            self._row.addWidget(btn)
        self._row.addStretch(1)

    def _change_instrument(self, name: str) -> None:
        data = run_cli("change_instrument", json.dumps({"name": name}, ensure_ascii=False))
        ok, reason = classify_cli_result(data)
        self._status.setText("" if ok else f"⚠️ '{name}' 장착 실패: {reason}")
        self.refresh()


class MusicPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_titles: list[str] = []
        self._current_title: str | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        player_row = QHBoxLayout()
        player_row.addWidget(self._build_left(), 1)
        player_row.addWidget(self._build_right(), 1)
        outer.addLayout(player_row, 1)

        self._instrument_bar = InstrumentBar()
        outer.addWidget(self._instrument_bar)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_activity)
        self._poll_timer.start(POLL_INTERVAL_MS)

    # -- layout ------------------------------------------------------------

    def _build_left(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)

        self._search = QLineEdit()
        self._search.setPlaceholderText("곡 검색")
        self._search.textChanged.connect(self._apply_filter)
        v.addWidget(self._search)

        self._catalog = SongCatalogList()
        self._catalog.itemDoubleClicked.connect(lambda item: self._enqueue(item.text()))
        v.addWidget(self._catalog, 1)
        return box

    def _build_right(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)

        self._now_playing = QLabel("재생 중인 곡 없음")
        self._now_playing.setWordWrap(True)
        self._now_playing.setStyleSheet("font-weight: 600;")
        v.addWidget(self._now_playing)

        btn_row = QHBoxLayout()
        play_btn = QPushButton("▶ 대기열 재생")
        play_btn.clicked.connect(self._play_next_in_queue)
        btn_row.addWidget(play_btn)
        stop_btn = QPushButton("⏹ 정지")
        stop_btn.clicked.connect(self._stop_playback)
        btn_row.addWidget(stop_btn)
        v.addLayout(btn_row)

        queue_row = QHBoxLayout()
        self._queue = QueueListWidget()
        self._queue.itemDoubleClicked.connect(self._play_specific_item)
        queue_row.addWidget(self._queue, 1)
        queue_row.addWidget(TrashZone(self._queue))
        v.addLayout(queue_row, 1)

        return box

    # -- catalog / search ----------------------------------------------------

    def refresh_songs(self) -> None:
        data = run_cli("get_music_scores")
        self._all_titles = (
            [item.get("DisplayTitle", "") for item in data if item.get("DisplayTitle")]
            if isinstance(data, list)
            else []
        )
        self._apply_filter(self._search.text())
        self._instrument_bar.refresh()

    def _apply_filter(self, text: str) -> None:
        self._catalog.clear()
        needle = text.strip().lower()
        for title in self._all_titles:
            if needle in title.lower():
                self._catalog.addItem(title)

    def _enqueue(self, title: str) -> None:
        self._queue.addItem(title)

    # -- playback --------------------------------------------------------

    def _play_next_in_queue(self) -> None:
        if self._queue.count() == 0:
            return
        item = self._queue.takeItem(0)
        self._start_playing(item.text())

    def _play_specific_item(self, item: QListWidgetItem) -> None:
        row = self._queue.row(item)
        if row >= 0:
            self._queue.takeItem(row)
        self._start_playing(item.text())

    def _start_playing(self, title: str) -> None:
        body = json.dumps({"title": title}, ensure_ascii=False)
        data = run_cli("play_music_score", body)
        ok, reason = classify_cli_result(data)
        if ok:
            self._current_title = title
            self._now_playing.setText(f"▶ {title}")
        else:
            self._current_title = None
            self._now_playing.setText(f"⚠️ '{title}' 재생 실패: {reason}")

    def _stop_playback(self) -> None:
        run_cli("stop_action")
        self._current_title = None
        self._now_playing.setText("재생 중인 곡 없음")

    def _poll_activity(self) -> None:
        if self._current_title is None:
            return
        data = run_cli("get_activity", timeout=15)
        performance = data.get("Performance", {}) if isinstance(data, dict) else {}
        if performance.get("IsPlaying", False):
            return
        # Song ended on its own - clear and move on to whatever's queued next.
        self._current_title = None
        self._now_playing.setText("재생 중인 곡 없음")
        self._play_next_in_queue()
