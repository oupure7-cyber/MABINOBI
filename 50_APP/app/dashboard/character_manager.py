"""'캐릭터 관리' dialog: lets the user see and edit what character_watcher.py has
detected so far (see app/character_profiles.py for the underlying data). A profile's
internal id (its filename) never changes - renaming only sets a separate display label,
and deleting only removes this app's local record, never anything in the game itself."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidgetItem, QInputDialog, QMessageBox)

from .. import character_profiles
from .ui_kit import STYLE, heading, button, table


class CharacterManagerDialog(QDialog):
    changed = Signal()

    def __init__(self, project_root: Path, parent=None):
        super().__init__(parent)
        self.project_root = project_root
        self.setWindowTitle('캐릭터 관리')
        self.resize(700, 440)
        self.setStyleSheet(STYLE)

        v = QVBoxLayout(self)
        v.addWidget(heading('캐릭터 관리'))
        guide = QLabel(
            '이 앱이 지금까지 알아본 캐릭터 목록입니다. 프로필 ID만으로는 어떤 캐릭터인지 알아보기 어려우니, '
            '아래에서 캐릭터를 선택하고 "이름 변경"으로 원하는 이름을 붙여두세요 - 붙여두면 화면 상단에도 '
            '그 이름으로 표시됩니다.'
        )
        guide.setWordWrap(True)
        v.addWidget(guide)

        self.table = table(['프로필 ID / 이름', '클래스', '서버', '최종 접속'])
        v.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addWidget(button('이름 변경', self.rename_selected))
        actions.addWidget(button('삭제', self.delete_selected))
        actions.addWidget(button('새로고침', self.refresh))
        actions.addStretch()
        actions.addWidget(button('닫기', self.close))
        v.addLayout(actions)

        warning = QLabel(
            '⚠️ "삭제"는 마비노비 앱이 저장해 둔 이 캐릭터의 로컬 기록(재화·인벤토리·캐릭터창고 스냅샷)만 '
            '지웁니다. 실제 게임 속 캐릭터나 아이템은 전혀 삭제되지 않으며, 그 캐릭터로 다시 접속하면 새 '
            '기록으로 다시 쌓입니다.'
        )
        warning.setWordWrap(True)
        warning.setStyleSheet('color: #d7b569;')
        v.addWidget(warning)

        self._profiles = []
        self.refresh()

    def refresh(self):
        self._profiles = sorted(
            character_profiles.load_profiles(self.project_root),
            key=lambda p: p.get('last_seen', ''), reverse=True,
        )
        self.table.setRowCount(len(self._profiles))
        for row, profile in enumerate(self._profiles):
            label = profile.get('custom_name') or profile['profile_id']
            id_item = QTableWidgetItem(label)
            id_item.setData(Qt.UserRole, profile['profile_id'])
            self.table.setItem(row, 0, id_item)
            self.table.setItem(row, 1, QTableWidgetItem(profile.get('class_name', '')))
            self.table.setItem(row, 2, QTableWidgetItem(profile.get('stats', {}).get('RealmName', '')))
            self.table.setItem(row, 3, QTableWidgetItem(character_profiles.format_last_seen(profile.get('last_seen', ''))))

    def _selected_profile_ids(self) -> list[str]:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        return [self.table.item(row, 0).data(Qt.UserRole) for row in rows]

    def rename_selected(self):
        ids = self._selected_profile_ids()
        if len(ids) != 1:
            QMessageBox.information(self, '이름 변경', '이름을 바꿀 캐릭터를 하나만 선택해주세요.')
            return
        profile = next(p for p in self._profiles if p['profile_id'] == ids[0])
        current = profile.get('custom_name') or profile['profile_id']
        text, ok = QInputDialog.getText(self, '이름 변경', '이 캐릭터를 부를 이름을 입력하세요:', text=current)
        if ok and text.strip():
            character_profiles.rename_profile(self.project_root, ids[0], text)
            self.refresh()
            self.changed.emit()

    def delete_selected(self):
        ids = self._selected_profile_ids()
        if not ids:
            QMessageBox.information(self, '삭제', '삭제할 캐릭터를 선택해주세요.')
            return
        reply = QMessageBox.question(
            self, '로컬 기록 삭제',
            f'선택한 {len(ids)}개 캐릭터의 로컬 기록을 삭제할까요?\n\n'
            '이 작업은 마비노비 앱에 저장된 기록만 지웁니다 - 실제 게임 캐릭터나 아이템은 영향받지 않습니다.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            for profile_id in ids:
                character_profiles.delete_profile(self.project_root, profile_id)
            self.refresh()
            self.changed.emit()
