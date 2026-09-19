"""'창고' tab: search for an item by name across every detected character's inventory,
캐릭터창고 and 계정창고. Pure search logic lives in app/character_profiles.py
(search_items()) - this is just the tab's widgets."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QTreeWidget, QTreeWidgetItem, QLabel)

from .. import character_profiles
from ..cli_client import run_cli
from .ui_kit import heading, button


class ItemsRefreshWorker(QThread):
    done = Signal(str, list, list)  # (profile_id, items, currencies)

    def __init__(self, profile_id: str, parent=None):
        super().__init__(parent)
        self.profile_id = profile_id

    def run(self) -> None:
        items = run_cli("get_items")
        currencies = run_cli("get_currencies")
        self.done.emit(
            self.profile_id,
            items if isinstance(items, list) else [],
            currencies if isinstance(currencies, list) else [],
        )


class StorageSearchPanel(QWidget):
    # Set by modern_window.py to a callable returning the currently-active profile's
    # id (or None if not identified yet) - loose-coupling like music_panel.guard.
    get_active_profile_id = None

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self._refresh_worker = None

        v = QVBoxLayout(self)
        v.addWidget(heading('창고 검색'))
        note = QLabel(
            '마비노기 AI 커넥터는 장비/도구/패션/펫·탈것의 정보를 제공하지 않습니다.\n'
            "다른 캐릭터들의 목록이 안 보이거나 클래스명만 보인다고요? 모든 캐릭터로 한 번씩 접속해보고, "
            "우측 상단의 '캐릭터 관리'를 확인해보세요!"
        )
        note.setWordWrap(True)
        v.addWidget(note)

        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('아이템 이름 검색')
        self.search.textChanged.connect(self.render_results)
        row.addWidget(self.search, 1)
        self.refresh_button = button('새로고침', self.refresh_active)
        row.addWidget(self.refresh_button)
        v.addLayout(row)

        self.status = QLabel('')
        self.status.setWordWrap(True)
        v.addWidget(self.status)

        # Always visible, never hidden/swapped for another widget - so the layout above
        # it (note/search row/status) never reflows just because the result count
        # changed. "No results" etc. are rendered as a placeholder row *inside* the
        # tree instead of toggling a separate label's visibility.
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['이름', '수량'])
        self.tree.setColumnWidth(0, 420)
        v.addWidget(self.tree, 1)

        self.render_results()

    def render_results(self, *_):
        profiles = character_profiles.load_profiles(self.project_root)
        self.tree.clear()
        if not profiles:
            self._show_placeholder('아직 감지된 캐릭터가 없습니다. 게임에 접속하면 자동으로 인식됩니다.')
            return

        groups = character_profiles.search_items(profiles, self.search.text())
        if not groups:
            self._show_placeholder('검색 결과가 없습니다.')
            return

        for group in groups:
            header = QTreeWidgetItem([group['label'], ''])
            bold = header.font(0)
            bold.setBold(True)
            header.setFont(0, bold)
            self.tree.addTopLevelItem(header)
            for item in group['items']:
                header.addChild(QTreeWidgetItem([item['name'], f"{item['count']:,}"]))
        self.tree.expandAll()

    def _show_placeholder(self, text: str) -> None:
        placeholder = QTreeWidgetItem([text, ''])
        placeholder.setFlags(placeholder.flags() & ~Qt.ItemIsSelectable)
        italic = placeholder.font(0)
        italic.setItalic(True)
        placeholder.setFont(0, italic)
        self.tree.addTopLevelItem(placeholder)

    def refresh_active(self):
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            return
        profile_id = self.get_active_profile_id() if self.get_active_profile_id else None
        if profile_id is None:
            self.status.setText('아직 활성 캐릭터를 확인하지 못했습니다. 잠시 후 다시 시도해주세요.')
            return
        self.status.setText('새로고침 중...')
        self.refresh_button.setEnabled(False)
        self._refresh_worker = ItemsRefreshWorker(profile_id, self)
        self._refresh_worker.done.connect(self._on_refreshed)
        self._refresh_worker.start()

    def _on_refreshed(self, profile_id: str, items: list, currencies: list) -> None:
        self.refresh_button.setEnabled(True)
        profile = character_profiles.refresh_items(self.project_root, profile_id, items, currencies)
        if profile is None:
            self.status.setText('새로고침 실패: 캐릭터 기록을 찾을 수 없습니다(캐릭터 관리에서 삭제되었을 수 있음).')
            return
        self.status.setText(f'새로고침 완료 · {character_profiles.display_name(profile)}')
        self.render_results()
