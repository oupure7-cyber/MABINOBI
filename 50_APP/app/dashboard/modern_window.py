"""Compact workspace. Existing CLI workers and original currency assets are reused."""
from __future__ import annotations

from pathlib import Path
import json
from PySide6.QtCore import Qt, QSettings, QTimer, QThread, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QTabWidget, QButtonGroup, QTableWidgetItem,
    QSplitter, QFrame, QGridLayout, QScrollArea, QPlainTextEdit, QComboBox, QMessageBox)

from .main_window import DashboardWindow as LegacyWindow, TopStatsPanel
from .widgets import CurrencyColumn, Toast, ToggleSwitch, HIDDEN_CURRENCY_NAMES, classify_cli_result
from .job_queue import JOB_CATALOG, JobSpec, QueuedJob, EQUIPMENT_WEEKLY_X10
from .equipment_crafting import TOWN_EQUIPMENT
from .altering_routine import AlteringRoutineWorker
from .routine_dashboard import RoutineDashboard
from .music_panel import MusicPanel
from ..cli_client import run_cli
from .job_drag import JobCatalogTable, JobDropTable
from .item_icons import item_icon, spec_item_name
from .character_watcher import CharacterWatcher
from .character_manager import CharacterManagerDialog
from .storage_search import StorageSearchPanel
from .. import character_profiles
from .ui_kit import STYLE, heading, button, table

def kind(spec):
    if spec.key.startswith('equipment_'): return '제작'
    return '채집' if spec.key.startswith('gather_') else '요리' if spec.key.startswith(('veggie_', 'cooking_')) else '무한가공소'

def title(spec):
    return spec.name.replace('채집: ', '').replace('요리: ', '').replace('제작: ', '').replace(' x100', '')

def quantity(spec, repeats=1):
    if kind(spec) == '제작':
        base = 10 if spec.key.startswith('equipment_x10_') else 2
        return f'목표 {base * repeats:,}개'
    if kind(spec) == '채집':
        return f'최대 {100 * repeats:,}개'
    if kind(spec) == '요리':
        return f'목표 {(50 if spec.key.endswith("50") else 10) * repeats:,}개'
    return '무한 반복' if spec.key == 'altering_infinite' else f'{repeats}시간'


class InfoWorker(QThread):
    result = Signal(object, object)
    def run(self):
        self.result.emit(run_cli('get_my_info'), run_cli('get_currencies'))


SCROLL_PREFIX = '제작 스크롤: '  # 임무 게시판에서 사는 퀘스트 아이템 - 인벤토리에만 보관 가능(창고 불가)


class ScrollInventoryWorker(QThread):
    result = Signal(list)
    def run(self):
        data = run_cli('get_items', json.dumps({'name': SCROLL_PREFIX}, ensure_ascii=False))
        self.result.emit(data if isinstance(data, list) else [])


class WorkQueue(QWidget):
    """Pause at a completed request boundary; never replay a partially crafted batch."""
    changed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs = []
        self.worker = None
        self.paused = True
        self.blocked = False
        self.skip = False
        self.interrupted = False
        self.activity_guard = lambda: False
        self.snapshot_target = None
        v = QVBoxLayout(self)
        self.header = heading('작업 대기열 · 0개 작업')
        v.addWidget(self.header)
        self.current_label = QLabel('대기 중 · 작업을 추가해주세요')
        self.current_label.setWordWrap(True)
        v.addWidget(self.current_label)
        controls = QHBoxLayout()
        self.pause_button = button('대기열 시작', self.toggle_pause)
        self.skip_button = button('현재 작업 건너뛰기', self.skip_current)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.skip_button)
        v.addLayout(controls)
        self.status = QLabel('추가한 작업은 시작 버튼을 누르면 순서대로 실행됩니다.')
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        self.list = table(['작업', '남은 실행 / 수량', '순서 · 삭제'], JobDropTable)
        self.list.setToolTip('왼쪽 목록의 아이템을 이곳으로 끌어 놓으세요.')
        v.addWidget(self.list, 1)
        self.warning = QLabel('무한가공소는 직접 건너뛰어야 다음 작업이 시작됩니다.')
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet('color: #d7b569; padding: 8px;')
        v.addWidget(self.warning)
        note = QLabel('채집 수량은 최대치이며 실제 획득량은 달라질 수 있습니다.')
        note.setWordWrap(True)
        v.addWidget(note)
        self.log_toggle = button('진행 기록 ▸', self.toggle_log)
        v.addWidget(self.log_toggle)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(300)
        self.log.setMaximumHeight(140)
        self.log.hide()
        v.addWidget(self.log)
        self.render()

    def toggle_log(self):
        self.log.setVisible(not self.log.isVisible())

    def add(self, spec):
        self.jobs.append(QueuedJob(spec, 1))
        self.message(f'대기열에 추가됨: {spec.name}')
        self.render()
        self.start_next()

    def message(self, text):
        self.status.setText(text)
        self.log.appendPlainText(text)
        self.changed.emit()

    def render(self):
        self.header.setText(f'작업 대기열 · {len(self.jobs)}개 작업')
        self.list.setRowCount(len(self.jobs))
        for i, job in enumerate(self.jobs):
            active = i == 0 and self.worker is not None
            self.list.setRowHeight(i, 52)
            item = QTableWidgetItem(f'{"▶ " if active else ""}{kind(job.spec)} · {title(job.spec)}')
            item.setIcon(item_icon(spec_item_name(job.spec)))
            item.setToolTip(job.spec.name)
            self.list.setItem(i, 0, item)
            box = QWidget(); row = QHBoxLayout(box); row.setContentsMargins(3, 2, 3, 2)
            dec = button('−', lambda _, j=job: self.bump(j, -1)); dec.setFixedWidth(30)
            inc = button('+', lambda _, j=job: self.bump(j, 1)); inc.setFixedWidth(30)
            finite = job.spec.key != 'altering_infinite'
            dec.setEnabled(not active and finite and job.repeats > 1)
            inc.setEnabled(not active and finite and job.repeats < 9)
            row.addWidget(dec)
            row.addWidget(QLabel(f'{job.repeats}회 · {quantity(job.spec, job.repeats)}' if finite else '무한 반복'))
            row.addWidget(inc)
            self.list.setCellWidget(i, 1, box)
            actions = QWidget(); a = QHBoxLayout(actions); a.setContentsMargins(2, 2, 2, 2)
            for label, offset in [('↑', -1), ('↓', 1)]:
                b = button(label, lambda _, j=job, d=offset: self.move_job(j, d)); b.setFixedWidth(29)
                b.setEnabled(not active and 0 <= i+offset < len(self.jobs) and not (self.worker and i+offset == 0))
                a.addWidget(b)
            remove = button('×', lambda _, j=job: self.remove(j)); remove.setFixedWidth(29)
            remove.setEnabled(not active); remove.setToolTip('대기열에서 삭제')
            a.addWidget(remove); self.list.setCellWidget(i, 2, actions)
        self.warning.setVisible(any(j.spec.key == 'altering_infinite' for j in self.jobs))
        self.pause_button.setText('게임 확인 후 재개' if self.blocked else '대기열 재개' if self.paused and self.jobs else '대기열 시작' if self.paused else '전체 일시정지')
        self.pause_button.setEnabled(bool(self.jobs) and not (self.paused and self.worker is not None))
        self.skip_button.setEnabled(self.worker is not None and not self.skip)
        self.current_label.setText(('실행 중 · ' if self.worker else '일시정지 · ' if self.paused else '대기 중 · ') + (self.jobs[0].spec.name if self.jobs else '작업 없음'))
        self.changed.emit()

    def bump(self, job, delta):
        job.repeats = max(1, min(9, job.repeats + delta)); self.render()

    def move_job(self, job, delta):
        i = self.jobs.index(job); n = i + delta
        if 0 <= n < len(self.jobs) and not (self.worker and (i == 0 or n == 0)):
            self.jobs[i], self.jobs[n] = self.jobs[n], self.jobs[i]; self.render()

    def remove(self, job):
        if self.worker and self.jobs[0] is job: return
        self.jobs.remove(job); self.render()

    def toggle_pause(self):
        if not self.paused:
            self.paused = True
            if self.worker and self.jobs[0].spec.key.startswith('altering_'):
                self.interrupted = True
                self.worker.request_stop()
            self.message('일시정지 요청: 이미 요청한 작업이 끝나면 멈춥니다.')
        else:
            if self.activity_guard():
                self.message('악보 연주를 정지한 뒤 작업을 시작해주세요.'); return
            self.paused = False; self.blocked = False
        self.render(); self.start_next()

    def skip_current(self):
        if self.worker:
            self.skip = True; self.worker.request_stop()
            self.message('건너뛰기 요청: 현재 요청이 종료되면 다음 작업으로 이동합니다.')
            self.render()

    def start_next(self):
        if self.paused or self.worker or not self.jobs: return
        if self.activity_guard():
            self.paused = True; self.message('악보 연주 중입니다. 연주 종료 후 재개해주세요.'); self.render(); return
        self.worker = self.jobs[0].spec.make_worker()
        if hasattr(self.worker, 'remaining') and hasattr(self.jobs[0], 'food_remaining'):
            self.worker.remaining = self.jobs[0].food_remaining
        self.worker.status.connect(self.message)
        self.worker.blocked.connect(self.on_blocked)
        # QThread.finished, not custom stopped: the old thread must have exited first.
        self.worker.finished.connect(self.on_finished)
        if isinstance(self.worker, AlteringRoutineWorker) and self.snapshot_target:
            self.snapshot_target._blocked = False
            self.snapshot_target._alert.hide(); self.snapshot_target._content.show()
            self.worker.snapshot.connect(self.snapshot_target._on_snapshot)
            self.worker.blocked.connect(self.snapshot_target._on_blocked)
        self.render(); self.worker.start()

    def on_blocked(self, reason):
        self.paused = True; self.blocked = True
        self.message(f'게임 화면 확인 필요: {reason}'); self.render()

    def on_finished(self):
        old = self.worker; self.worker = None
        if self.jobs and hasattr(old, 'remaining'):
            if self.blocked: self.jobs[0].food_remaining = old.remaining
            elif hasattr(self.jobs[0], 'food_remaining'): del self.jobs[0].food_remaining
        if not self.blocked and self.jobs:
            if self.skip: self.jobs.pop(0)
            elif not self.interrupted:
                self.jobs[0].repeats -= 1
                if self.jobs[0].repeats <= 0: self.jobs.pop(0)
        self.skip = False; self.interrupted = False
        if not self.jobs: self.paused = True
        old.deleteLater(); self.render(); self.start_next()


class CompactInstruments(QWidget):
    def __init__(self, player):
        super().__init__()
        self.player = player
        row = QHBoxLayout(self); row.setContentsMargins(0, 0, 0, 6)
        row.addWidget(QLabel('악기 선택'))
        self.combo = QComboBox(); self.combo.setMinimumWidth(230)
        self.combo.addItem('게임 연결 후 악기 표시', None)
        row.addWidget(self.combo)
        row.addWidget(button('악기 변경', self.change))
        self.status = QLabel(''); row.addWidget(self.status, 1)
        self.setMaximumHeight(48)

    def refresh(self):
        data = run_cli('get_instruments')
        if not isinstance(data, list):
            self.status.setText('악기 목록을 불러오지 못했습니다.'); return
        self.combo.clear()
        for entry in data:
            name = entry.get('Name', '')
            self.combo.addItem(name, name)
            if entry.get('IsEquipped'): self.combo.setCurrentIndex(self.combo.count()-1)

    def change(self):
        if self.player.guard() or self.player._current_title:
            self.status.setText('작업과 연주를 정지한 후 변경해주세요.'); return
        name = self.combo.currentData()
        if not name: return
        ok, reason = classify_cli_result(run_cli('change_instrument', json.dumps({'name': name}, ensure_ascii=False)))
        self.status.setText('악기를 변경했습니다.' if ok else f'변경 실패: {reason}')
        if ok: self.refresh()


class ScorePanel(MusicPanel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.guard = lambda: False
        old = self._instrument_bar
        self.layout().removeWidget(old); old.hide(); old.deleteLater()
        self._instrument_bar = CompactInstruments(self)
        self.layout().insertWidget(0, self._instrument_bar)
        self.layout().insertWidget(0, heading('악보 연주'))
        self._search.setPlaceholderText('악보 이름 검색')
        # Keep the original score/instrument retrieval and playback logic.
        left = self._search.parentWidget().layout()
        left.insertWidget(0, heading('보유 악보'))
        left.addWidget(button('선택한 악보를 대기열에 추가', self.add_selected))
        right = self._queue.parentWidget().layout()
        right.insertWidget(0, heading('연주 대기열'))
        for zone in self.findChildren(QLabel):
            if zone.text() == '🗑': zone.hide()
        right.addWidget(button('선택한 악보 삭제', self.remove_selected))
        self._queue.setToolTip('악보를 끌어 순서를 변경할 수 있습니다.')

    def add_selected(self):
        item = self._catalog.currentItem()
        if item: self._enqueue(item.text())

    def remove_selected(self):
        row = self._queue.currentRow()
        if row >= 0: self._queue.takeItem(row)

    def _play_next_in_queue(self):
        if self.guard():
            self._now_playing.setText('작업을 일시정지하고 현재 요청이 끝난 뒤 연주해주세요.'); return
        super()._play_next_in_queue()

    def _play_specific_item(self, item):
        if self.guard():
            self._now_playing.setText('작업을 일시정지하고 현재 요청이 끝난 뒤 연주해주세요.'); return
        super()._play_specific_item(item)

    def _stop_playback(self):
        if self._current_title is not None: super()._stop_playback()


class DashboardWindow(LegacyWindow):
    def __init__(self, project_root: Path, *, connect_on_start: bool = True):
        # Reuse connection/onboarding behavior without constructing the legacy layout.
        from PySide6.QtWidgets import QMainWindow
        QMainWindow.__init__(self)
        self.project_root = project_root
        self.setWindowTitle('마비노비')
        self.setMinimumSize(1100, 700)
        self._fit_to_active_screen()
        self.setStyleSheet(STYLE)
        self._connection_worker = None; self._guide_dialog = None; self.info_worker = None
        self._scroll_worker = None
        self.settings = QSettings('MabiNobi', 'Workspace')
        self.recent = self.settings.value('recent', [], type=list)
        self.category = '채집'; self.filter_mode = '전체'
        self.specs = [JobSpec(s.key, '무한가공소 · 1시간' if s.key == 'altering_1h' else s.name, s.make_worker) for s in JOB_CATALOG]
        self.specs.append(JobSpec('altering_infinite', '무한가공소', AlteringRoutineWorker))
        self.currency_data = []
        central = QWidget(); outer = QVBoxLayout(central); outer.setContentsMargins(22, 12, 22, 16); outer.setSpacing(12)
        self.setCentralWidget(central)
        toolbar = QHBoxLayout()
        self.character_btn = button('캐릭터 정보 ▾', self.toggle_info)
        toolbar.addWidget(self.character_btn)
        self.active_character_label = QLabel(''); toolbar.addWidget(self.active_character_label)
        self.wings = QLabel('정령의 날개  —'); toolbar.addWidget(self.wings)
        toolbar.addWidget(button('주요 재화 ▾', self.show_currencies)); toolbar.addStretch()
        toolbar.addWidget(QLabel('게임 연결'))
        self.connection_toggle = ToggleSwitch(); self.connection_toggle.toggled.connect(self._on_toggle)
        toolbar.addWidget(self.connection_toggle)
        toolbar.addWidget(button('새로고침', self.refresh_all))
        toolbar.addWidget(button('캐릭터 관리', self.open_character_manager))
        outer.addLayout(toolbar)
        self.tabs = QTabWidget(); outer.addWidget(self.tabs, 1)
        work = QWidget(); w = QHBoxLayout(work); w.setContentsMargins(0, 12, 0, 0)
        self.split = QSplitter(Qt.Horizontal); w.addWidget(self.split)
        left = QWidget(); lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 18, 0)
        lv.addWidget(heading('작업 선택'))
        cats = QHBoxLayout(); group = QButtonGroup(self)
        for name in ['채집', '요리', '제작', '무한가공소']:
            b = button(name, lambda _, n=name: self.select_category(n)); b.setCheckable(True); b.setChecked(name == self.category)
            group.addButton(b); cats.addWidget(b)
        cats.addStretch(); lv.addLayout(cats)
        self.equipment_buttons = QWidget(); eqv = QVBoxLayout(self.equipment_buttons)
        eqv.setContentsMargins(0, 0, 0, 6); eqv.setSpacing(6)
        eqv.addWidget(button('보유 스크롤 모두 진행', self.craft_all_owned_scrolls))
        weekly = QHBoxLayout()
        for town in TOWN_EQUIPMENT:
            weekly.addWidget(button(f'주간 제작({town})', lambda _, t=town: self.add_weekly_equipment(t, 1)))
        eqv.addLayout(weekly)
        weekly_x5 = QHBoxLayout()
        for town in TOWN_EQUIPMENT:
            weekly_x5.addWidget(button(f'주간 제작({town}) x5', lambda _, t=town: self.add_weekly_equipment(t, 5)))
        eqv.addLayout(weekly_x5)
        lv.addWidget(self.equipment_buttons); self.equipment_buttons.hide()
        search = QHBoxLayout(); self.search = QLineEdit(); self.search.setPlaceholderText('재료 또는 작업 이름 검색')
        self.search.textChanged.connect(self.render_catalog); search.addWidget(self.search, 1)
        filters = QButtonGroup(self)
        for name in ['전체', '최근 사용']:
            b = button(name, lambda _, n=name: self.set_filter(n)); b.setCheckable(True); b.setChecked(name == '전체')
            filters.addButton(b); search.addWidget(b)
        lv.addLayout(search)
        self.catalog = table(['재료 / 작업', '1회 기준'], JobCatalogTable)
        lv.addWidget(self.catalog, 1)
        self.empty = QLabel(''); self.empty.setWordWrap(True); lv.addWidget(self.empty)
        self.routine = RoutineDashboard()
        self.routine.setWindowFlags(Qt.Widget); self.routine.setAttribute(Qt.WA_DeleteOnClose, False)
        lv.addWidget(self.routine, 1); self.routine.hide()
        self.catalog_note = QLabel('아이템을 오른쪽 대기열로 드래그한 뒤 시작하세요.')
        self.catalog_note.setWordWrap(True); lv.addWidget(self.catalog_note)
        self.queue = WorkQueue(); self.queue.snapshot_target = self.routine
        self.queue.list.jobDropped.connect(self.add_job_key)
        self.split.addWidget(left); self.split.addWidget(self.queue); self.split.setSizes([700, 720])
        self.tabs.addTab(work, '작업')
        self.music_panel = ScorePanel(); self.tabs.addTab(self.music_panel, '악보')
        self.storage_panel = StorageSearchPanel(self.project_root); self.tabs.addTab(self.storage_panel, '창고')
        self.storage_panel.get_active_profile_id = lambda: self._active_profile_id
        self.music_panel.guard = lambda: self.queue.worker is not None or not self.queue.paused
        self.queue.activity_guard = lambda: self.music_panel._current_title is not None
        self.music_status = QLabel(''); self.music_panel.layout().insertWidget(1, self.music_status)
        self.queue.changed.connect(lambda: self.music_status.setText(self.queue.current_label.text()))
        self.make_info_panel()
        self.toast = Toast(self)
        self.render_catalog()
        self.character_watcher = None
        self._active_profile_id = None
        self._character_manager_dialog = None
        if connect_on_start:
            self._try_connect()
            self.character_watcher = CharacterWatcher(self.project_root, parent=self)
            self.character_watcher.profile_updated.connect(self._on_profile_updated)

    def _on_profile_updated(self, profile, all_profiles):
        self._active_profile_id = profile['profile_id']
        self.active_character_label.setText(character_profiles.display_name(profile))

    def refresh_active_character_label(self):
        """Re-render the toolbar label from disk - e.g. after a rename/delete in 캐릭터 관리."""
        if self._active_profile_id is None:
            return
        profiles = character_profiles.load_profiles(self.project_root)
        current = next((p for p in profiles if p['profile_id'] == self._active_profile_id), None)
        self.active_character_label.setText(character_profiles.display_name(current) if current else '')

    def open_character_manager(self):
        if self._character_manager_dialog is None:
            self._character_manager_dialog = CharacterManagerDialog(self.project_root, self)
            self._character_manager_dialog.changed.connect(self.refresh_active_character_label)
        self._character_manager_dialog.refresh()
        self._character_manager_dialog.show()
        self._character_manager_dialog.raise_()
        self._character_manager_dialog.activateWindow()

    def select_category(self, name):
        self.category = name; self.render_catalog()

    def set_filter(self, name):
        self.filter_mode = name; self.render_catalog()

    def render_catalog(self, *_):
        self.catalog_note.setText('새 요리는 목표 수량 이상을 1회씩 제작합니다. 제작 호출마다 정령의 날개 5개가 소모되며, 별도 준비가 필요한 재료는 안내 후 멈춥니다.' if self.category == '요리' else '아이템을 오른쪽 대기열로 드래그한 뒤 시작하세요.')
        needle = self.search.text().strip().lower()
        if self.category == '제작':
            self.catalog_note.setText('오른쪽 대기열로 드래그하세요. 요청 1회마다 정령의 날개 5개 소모. x5 스크롤이 가장 경제적입니다!\n별도 가공/구매 재료가 부족하면 안내 후 멈춥니다.')
        specs = [s for s in self.specs if kind(s) == self.category and needle in s.name.lower()]
        if self.filter_mode == '최근 사용': specs = sorted([s for s in specs if s.key in self.recent], key=lambda s: self.recent.index(s.key))
        self.catalog.setRowCount(len(specs))
        for i, spec in enumerate(specs):
            self.catalog.setRowHeight(i, 36)
            item = QTableWidgetItem(item_icon(spec_item_name(spec)), title(spec))
            item.setData(Qt.UserRole, spec.key)
            item.setToolTip('오른쪽 대기열로 드래그하여 추가')
            self.catalog.setItem(i, 0, item)
            self.catalog.setItem(i, 1, QTableWidgetItem('  ' + quantity(spec) + '  '))
        self.empty.setText('검색 결과가 없습니다.' if not specs else '')
        self.empty.setVisible(not specs)
        self.equipment_buttons.setVisible(self.category == '제작')
        self.routine.setVisible(self.category == '무한가공소')
        self.catalog.setMaximumHeight(125 if self.category == '무한가공소' else 16777215)

    def add_job_key(self, key):
        spec = next((s for s in self.specs if s.key == key), None)
        if spec is not None: self.add_job(spec)

    def add_job(self, spec):
        self.queue.add(spec)
        self.recent = [spec.key] + [k for k in self.recent if k != spec.key]
        self.settings.setValue('recent', self.recent[:30])
        self.toast.show_message(f'대기열에 추가됨 · {title(spec)}')

    def add_weekly_equipment(self, town, weeks):
        """'주간 제작(마을)'/'x5' buttons - queue that town's 3 scroll recipes at once.
        x5 uses the hidden x10 job (5 weeks' worth batched into as few execute_crafting
        calls as the facility allows) instead of adding the x2 job with repeats=5, which
        would re-run the whole x2 job 5 separate times (user request, 2026-09-20)."""
        for recipe in TOWN_EQUIPMENT[town]:
            if weeks == 5:
                spec = EQUIPMENT_WEEKLY_X10[recipe]
            else:
                spec = next(s for s in self.specs if s.key == f'equipment_{recipe}')
            self.add_job(spec)

    def _find_equipment_spec(self, recipe_name):
        """Match a scroll-derived recipe name to a catalog spec, tolerant of whitespace
        differences - the live API is known to be inconsistent about spacing within an
        item name (recipe_info() already normalizes for the same reason when matching
        get_craftable_items)."""
        target = ''.join(recipe_name.split()).casefold()
        for s in self.specs:
            if s.key.startswith('equipment_') and ''.join(s.key[len('equipment_'):].split()).casefold() == target:
                return s
        return None

    def craft_all_owned_scrolls(self):
        """'보유 스크롤 모두 진행' - 인벤토리의 "제작 스크롤: <이름>"을 전부 확인해서, 아는
        레시피(EQUIPMENT_RECIPES)면 그 개수만큼 반복(◀N▶)으로 대기열에 추가한다. 스크롤은
        창고(캐릭터창고/계정창고)엔 보관이 안 되는 아이템이라 인벤토리만 본다. 모르는
        스크롤(아직 JOB으로 안 만든 다른 제작 종류)은 조용히 건너뛴다(user, 2026-09-20)."""
        if self._scroll_worker is not None and self._scroll_worker.isRunning():
            return
        self.toast.show_message('보유 스크롤 확인 중...')
        self._scroll_worker = ScrollInventoryWorker(self)
        self._scroll_worker.result.connect(self._on_scrolls_loaded)
        self._scroll_worker.start()

    def _on_scrolls_loaded(self, items):
        added = []
        unknown = 0
        for item in items:
            name = item.get('DisplayName', '')
            if item.get('Location') != 'inventory' or not name.startswith(SCROLL_PREFIX):
                continue
            recipe = name[len(SCROLL_PREFIX):]
            spec = self._find_equipment_spec(recipe)
            if spec is None:
                unknown += 1
                continue
            count = item.get('Count', 0)
            if count <= 0:
                continue
            repeats = max(1, min(9, count))
            self.queue.jobs.append(QueuedJob(spec, repeats))
            self.recent = [spec.key] + [k for k in self.recent if k != spec.key]
            added.append(f'{title(spec)} x{repeats}')
        if added:
            self.settings.setValue('recent', self.recent[:30])
            self.queue.render(); self.queue.start_next()
            summary = ', '.join(added)
            if unknown: summary += f' (모르는 스크롤 {unknown}종 제외)'
            self.queue.message(f'스크롤 대기열 추가: {summary}')
            self.toast.show_message(f'스크롤 {len(added)}종 대기열에 추가됨', 4000)
        elif unknown:
            self.toast.show_message(f'모르는 스크롤 {unknown}종만 있어 건너뛰었습니다.')
        else:
            self.toast.show_message('보유한 제작 스크롤이 없습니다.')

    def make_info_panel(self):
        self.info = QFrame(self.centralWidget()); self.info.setObjectName('infoPanel')
        v = QVBoxLayout(self.info)
        bar = QHBoxLayout(); bar.addWidget(heading('캐릭터 정보'), 1)
        bar.addWidget(button('새로고침', self.refresh_all)); bar.addWidget(button('×', self.info.hide)); v.addLayout(bar)
        self.top_stats = TopStatsPanel(); v.addWidget(self.top_stats)
        stat_names = ['전투력', '생활력', '매력', '마도 저항', '공격력', '최대 체력', '방어력', '데코 점수', '힘', '솜씨', '지력', '행운']
        for (name, value), text in zip(self.top_stats._cells.values(), stat_names):
            name.setText(text); name.setStyleSheet('color: #9aabb3; font-size: 12px;')
            value.setStyleSheet('font-size: 16px; font-weight: 600; padding-bottom: 10px;')
        v.addWidget(heading('보유 재화'))
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        host = QWidget(); self.currency_grid = QGridLayout(host); self.currency_grid.setAlignment(Qt.AlignTop)
        scroll.setWidget(host); v.addWidget(scroll, 1)
        self.currency_column = CurrencyColumn()  # original asset lookup/row renderer
        self.currency_column.hide(); self.info.hide()

    def toggle_info(self):
        if self.info.isVisible(): self.info.hide()
        else:
            self.info.setGeometry(12, 58, min(740, self.centralWidget().width()-24), self.centralWidget().height()-74)
            self.info.show(); self.info.raise_()

    def show_currencies(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        for r in self.currency_data:
            if r.get('DisplayName') in ['정령의 날개', '골드', '데카', 'M캐시']:
                menu.addAction(f'{r["DisplayName"]}   {r.get("Amount", 0):,}').setEnabled(False)
        if menu.isEmpty(): menu.addAction('게임 연결 후 표시됩니다.').setEnabled(False)
        menu.addSeparator(); menu.addAction('전체 재화 보기', self.toggle_info)
        menu.exec(self.sender().mapToGlobal(self.sender().rect().bottomLeft()))

    def refresh_all(self):
        if self.info_worker and self.info_worker.isRunning(): return
        if self.queue.worker or self.music_panel._current_title:
            self.toast.show_message('현재 작업이 끝난 뒤 정보를 새로고침해주세요.'); return
        self.info_worker = InfoWorker(self); self.info_worker.result.connect(self.update_info); self.info_worker.start()
        if self.music_panel._current_title is None and self.queue.worker is None:
            self.music_panel.refresh_songs()

    def update_info(self, stats, currencies):
        self.top_stats.set_data(stats)
        if not isinstance(currencies, list): return
        self.currency_data = currencies
        while self.currency_grid.count():
            item = self.currency_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        rows = [r for r in currencies if r.get('DisplayName') not in HIDDEN_CURRENCY_NAMES]
        midpoint = (len(rows)+1)//2
        for i, r in enumerate(rows):
            name = r.get('DisplayName', ''); amount = r.get('Amount', 0)
            chip = self.currency_column._make_row(name, amount)
            chip.setFixedHeight(38)
            chip.setStyleSheet('QFrame { background: transparent; border-bottom: 1px solid #30454c; border-radius: 0; }')
            self.currency_grid.addWidget(chip, i % midpoint, i // midpoint)
            if name == '정령의 날개': self.wings.setText(f'정령의 날개  {amount:,}')

    def _fit_to_active_screen(self):
        """Size to 80% of, and center on, whichever screen the cursor is currently on -
        so the window never starts larger than the monitor the user is actually at."""
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        avail = screen.availableGeometry()
        self.resize(int(avail.width() * 0.8), int(avail.height() * 0.8))
        # Re-read the actual size: resize() above is clamped to setMinimumSize(), so on
        # a very small screen the real size can end up bigger than the 80% requested.
        w, h = self.width(), self.height()
        self.move(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'info') and self.info.isVisible():
            self.info.setGeometry(12, 58, min(740, self.centralWidget().width()-24), self.centralWidget().height()-74)

    def closeEvent(self, event):
        workers = [self.queue.worker, self._connection_worker, self.info_worker]
        if any(w is not None and w.isRunning() for w in workers):
            self.queue.paused = True
            if self.queue.worker: self.queue.worker.request_stop()
            self.toast.show_message('실행 중인 요청이 끝난 뒤 다시 닫아주세요.', 4000)
            self.queue.render(); event.ignore(); return
        if self.music_panel._current_title:
            self.music_panel._stop_playback()
        if self.character_watcher is not None:
            self.character_watcher.stop()
        self.routine.close(); event.accept()
