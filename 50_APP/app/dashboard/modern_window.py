"""Compact workspace. Existing CLI workers and original currency assets are reused."""
from __future__ import annotations

from pathlib import Path
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from time import monotonic
from PySide6.QtCore import Qt, QSettings, QTimer, QThread, Signal, QSize
from PySide6.QtGui import QCursor, QColor
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTabWidget, QButtonGroup, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QFrame, QGridLayout, QScrollArea, QPlainTextEdit, QComboBox, QMessageBox,
    QSpinBox, QCheckBox, QSlider)

from .main_window import DashboardWindow as LegacyWindow, TopStatsPanel
from .widgets import CurrencyColumn, Toast, ToggleSwitch, HIDDEN_CURRENCY_NAMES, classify_cli_result
from .job_queue import JOB_CATALOG, JobSpec, QueuedJob, EQUIPMENT_WEEKLY_X6, EQUIPMENT_WEEKLY_X10, EQUIPMENT_WEEKLY_X5
from .equipment_crafting import TOWN_EQUIPMENT
from .altering_routine import AlteringRoutineWorker
from .routine_dashboard import RoutineDashboard
from .music_panel import MusicPanel
from ..cli_client import run_cli
from .job_drag import JobCatalogTable, JobDropTable
from .item_icons import item_icon, spec_item_name
from .gather_catalog import GatherCatalogWorker, parse_gather_items, gather_state
from .gather_job import GatherJobWorker
from .crafting_catalog import (RecipeCatalogWorker, parse_recipes, recipe_state,
                              reference_recipes, merge_reference_recipes, catalogue_sort_key)
from .crafting_detail import CraftingDetail
from .crafting_engine import CraftingWorker
from .progress_overlay import ProgressOverlay
from .overlay import EnvironmentOverlayController

from .character_watcher import CharacterWatcher
from .character_manager import CharacterManagerDialog
from .storage_search import StorageSearchPanel
from .. import character_profiles
from .ui_kit import STYLE, heading, button, table, OwnedCountDelegate, OWNED_COUNT_ROLE, OWNED_COUNT_COLOR
from .owned_items import OwnedItemsIndex, OwnedItemCounts

def kind(spec):
    if spec.key.startswith('craft:'): return '제작'
    if spec.key.startswith('equipment_'): return '제작'
    return '채집' if spec.key.startswith('gather_') else '요리' if spec.key.startswith(('veggie_', 'cooking_')) else '무한가공소'

def title(spec):
    if kind(spec) == '제작': return spec_item_name(spec)
    return spec.name.replace('채집: ', '').replace('요리: ', '').replace('제작: ', '').replace(' x100', '')

def quantity(spec, repeats=1):
    if getattr(spec, 'target_count', 0): return f'목표 {spec.target_count * repeats:,}개'
    if kind(spec) == '제작':
        # Ask a freshly-constructed (never-started) worker for its own real target
        # instead of hardcoding per-variant numbers here - stays correct automatically
        # as new hidden x6/x10/x5-style variants are added (they all set
        # RecipeCookingWorker.remaining in __init__, before any CLI call happens).
        base = spec.make_worker().remaining
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
    progress = Signal(object)
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
        self.last_progress = {}
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
            self.list.setRowHeight(i, 40)
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
            if job.spec.target_count:
                for position in reversed(range(row.count())):
                    existing = row.takeAt(position).widget()
                    if existing: existing.deleteLater()
                count_input = QSpinBox(); count_input.setRange(1, 9999); count_input.setValue(job.spec.target_count)
                count_input.setSuffix('개'); count_input.setKeyboardTracking(False)
                count_input.setEnabled(not active and not hasattr(job, 'craft_checkpoint'))
                count_input.setToolTip('목표 수량 · 작업 시작 전 변경할 수 있습니다.')
                count_input.valueChanged.connect(lambda n, j=job:self.change_target(j, n))
                row.addWidget(count_input)
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

    def change_target(self, job, amount):
        if job not in self.jobs or hasattr(job, 'craft_checkpoint') or (self.worker and self.jobs[0] is job): return
        name = job.spec.recipe_name
        job.spec = replace(job.spec, target_count=amount, make_worker=lambda r=name, n=amount:CraftingWorker(r,n))
        self.changed.emit()

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
            if self.worker and (self.jobs[0].spec.key.startswith('altering_') or isinstance(self.worker, CraftingWorker)):
                self.interrupted = True
                self.worker.request_stop()
            self.message('일시정지 요청: 이미 요청한 작업이 끝나면 멈춥니다.')
        else:
            if self.activity_guard():
                self.message('연주나 정보 조회가 끝난 뒤 작업을 시작해주세요.'); return
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
            self.paused = True; self.message('연주나 정보 조회가 끝난 뒤 재개해주세요.'); self.render(); return
        self.last_progress = {'recipe':spec_item_name(self.jobs[0].spec), 'target':self.jobs[0].spec.target_count,
                              'completed':0, 'stage':'준비', 'materials':[]}
        self.progress.emit(self.last_progress)
        self.worker = self.jobs[0].spec.make_worker()
        if isinstance(self.worker, CraftingWorker) and hasattr(self.jobs[0], 'craft_checkpoint'):
            self.worker.checkpoint = deepcopy(self.jobs[0].craft_checkpoint)
        if hasattr(self.worker, 'remaining') and hasattr(self.jobs[0], 'food_remaining'):
            self.worker.remaining = self.jobs[0].food_remaining
        self.worker.status.connect(self.message)
        self.worker.blocked.connect(self.on_blocked)
        if hasattr(self.worker, 'progress'):
            self.worker.progress.connect(self.on_progress)
        # QThread.finished, not custom stopped: the old thread must have exited first.
        self.worker.finished.connect(self.on_finished)
        if isinstance(self.worker, AlteringRoutineWorker) and self.snapshot_target:
            self.snapshot_target._blocked = False
            self.snapshot_target._alert.hide(); self.snapshot_target._content.show()
            self.worker.snapshot.connect(self.snapshot_target._on_snapshot)
            self.worker.snapshot.connect(self.on_routine_snapshot)
            self.worker.blocked.connect(self.snapshot_target._on_blocked)
            self.snapshot_target.wire_targets(self.worker)
        self.render(); self.worker.start()

    def on_blocked(self, reason):
        if self.skip: return
        self.paused = True; self.blocked = True
        self.message(f'게임 화면 확인 필요: {reason}'); self.render()

    def on_finished(self):
        old = self.worker; self.worker = None
        if self.jobs and isinstance(old, CraftingWorker):
            self.jobs[0].craft_checkpoint = deepcopy(old.checkpoint)
        if self.skip:
            if self.jobs: self.jobs.pop(0)
            self.blocked = False
        elif self.interrupted:
            self.paused = True
        if self.jobs and hasattr(old, 'remaining') and not self.skip and not isinstance(old, CraftingWorker):
            if self.blocked: self.jobs[0].food_remaining = old.remaining
            elif hasattr(self.jobs[0], 'food_remaining'): del self.jobs[0].food_remaining
        if not self.blocked and self.jobs and not self.skip:
            if not self.interrupted:
                self.jobs[0].repeats -= 1
                if hasattr(self.jobs[0], 'craft_checkpoint'): del self.jobs[0].craft_checkpoint
                if self.jobs[0].repeats <= 0: self.jobs.pop(0)
        was_interrupted = self.interrupted
        self.skip = False; self.interrupted = False
        if not self.jobs: self.paused = True
        if self.last_progress:
            self.last_progress['stage'] = '일시정지' if self.blocked or was_interrupted else '완료'
            self.progress.emit(deepcopy(self.last_progress))
        old.deleteLater(); self.render(); self.start_next()

    def on_progress(self, data):
        self.last_progress = deepcopy(data)
        self.progress.emit(self.last_progress)

    def on_routine_snapshot(self, data):
        from .altering_routine import FAMILIES, QUEUE_CAPACITY
        rows = []
        for family in FAMILIES:
            control = getattr(self.snapshot_target, '_controls', {}).get(family.key)
            target = control.value() if control is not None else family.default_target_idx
            tier = family.tiers[max(0, min(len(family.tiers) - 1, target))]
            occupied = data.get('queue', {}).get(family.key, 0)
            done = data.get('queue_completed', {}).get(family.key, 0)
            rows.append({'name': tier.name, 'owned': done, 'required': occupied,
                         'state': f'시설 {occupied}/{QUEUE_CAPACITY} · 완료 {done}'})
        self.on_progress({'recipe': '무한가공소', 'target': 0, 'completed': 0,
                          'stage': '가공', 'materials': rows, 'message': self.status.text()})


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
    def __init__(self, project_root: Path, *, connect_on_start: bool = True, settings=None):
        # Reuse connection/onboarding behavior without constructing the legacy layout.
        from PySide6.QtWidgets import QMainWindow
        QMainWindow.__init__(self)
        self.project_root = project_root
        self.setWindowTitle('마비노비')
        self.setMinimumSize(1100, 700)
        self._fit_to_active_screen()
        self.setStyleSheet(STYLE)
        self._connection_worker = None; self._guide_dialog = None; self.info_worker = None
        self.catalog_worker = None
        self.gather_rows = None
        self.owned_items = OwnedItemsIndex.from_profile(None)
        self._owned_checked_at = None
        self._owned_clock = ''
        self._owned_columns = ()
        self.recipe_rows = reference_recipes(); self.catalog_counts = {}; self.catalog_loaded = False
        self.category_buttons = {}
        self.settings = settings if settings is not None else QSettings('MabiNobi', 'Workspace')
        self._scroll_worker = None
        self.recent = self.settings.value('recent', [], type=list)
        self.category = '채집'; self.filter_mode = '전체'
        self.specs = [JobSpec(s.key, '무한가공소 · 1시간' if s.key == 'altering_1h' else s.name, s.make_worker) for s in JOB_CATALOG]
        self.specs.append(JobSpec('altering_infinite', '무한가공소', AlteringRoutineWorker))
        # The requested consumables are present even before connecting. These
        # defaults contain no invented ingredient requirements or ready state.
        for name, row in self.recipe_rows.items():
            amount = row.get('ProducedPerCraft', 1)
            self.specs.append(JobSpec('craft:' + name, '제작: ' + name,
                                     lambda r=name, n=amount: CraftingWorker(r,n), amount, name))
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
        self.overlay_button = QPushButton('오버레이'); self.overlay_button.setCheckable(True)
        self.overlay_button.toggled.connect(self._on_overlay_toggled)
        toolbar.addWidget(self.overlay_button)
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
            self.category_buttons[name] = b
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
        sync_row = QHBoxLayout()
        self.catalog_status = QLabel(f'소모품·재료·생활 아이템 {len(self.recipe_rows)}종 등록 · 게임 연결 후 제작 조건을 확인합니다.')
        self.catalog_status.setStyleSheet('color: #9aabb3; font-size: 12px;')
        self.catalog_status.setWordWrap(True)
        self.sync_button = button('제작 목록 동기화', self.sync_recipes)
        sync_row.addWidget(self.catalog_status, 1); sync_row.addWidget(self.sync_button)
        lv.addLayout(sync_row)
        gather_sync_row = QHBoxLayout()
        self.gather_status = QLabel('채집 참고 목록 128종 · 게임 연결 후 숙련도와 도구 조건을 확인하세요.')
        self.gather_status.setWordWrap(True)
        self.gather_sync_button = button('채집 목록 동기화', self.sync_gathering)
        gather_sync_row.addWidget(self.gather_status, 1)
        gather_sync_row.addWidget(self.gather_sync_button)
        lv.addLayout(gather_sync_row)
        self.owned_status = QLabel('보유 수량 확인 전 · 창고 = 캐릭터 창고 + 계정 창고')
        self.owned_status.setStyleSheet('color: #b9c8cd; font-size: 12px;')
        self.owned_status.setWordWrap(True)
        lv.addWidget(self.owned_status)
        self.catalog = table(['재료 / 작업', '1회 기준'], JobCatalogTable)
        self.catalog.setItemDelegate(OwnedCountDelegate(self.catalog))
        self.catalog.itemSelectionChanged.connect(self.show_recipe_detail)
        lv.addWidget(self.catalog, 1)
        self.empty = QLabel(''); self.empty.setWordWrap(True); lv.addWidget(self.empty)
        self.routine = RoutineDashboard()
        self.routine.setWindowFlags(Qt.Widget); self.routine.setAttribute(Qt.WA_DeleteOnClose, False)
        lv.addWidget(self.routine, 1); self.routine.hide()
        self.craft_detail = CraftingDetail(); self.craft_detail.hide(); lv.addWidget(self.craft_detail)
        self.catalog_note = QLabel('아이템을 오른쪽 대기열로 드래그한 뒤 시작하세요.')
        self.catalog_note.setWordWrap(True); lv.addWidget(self.catalog_note)
        self.queue = WorkQueue(); self.queue.snapshot_target = self.routine
        self.queue.list.jobDropped.connect(self.add_job_key)
        self.split.addWidget(left); self.split.addWidget(self.queue); self.split.setSizes([900, 570])
        self.tabs.addTab(work, '작업')
        self.music_panel = ScorePanel(); self.tabs.addTab(self.music_panel, '악보')
        self.music_panel.guard = lambda: self.queue.worker is not None or not self.queue.paused or self.query_busy()
        self.queue.activity_guard = lambda: self.music_panel._current_title is not None or self.query_busy()
        self.overlay = ProgressOverlay(self.settings, self)
        self.overlay.set_enabled(False)
        self.environment_overlay = EnvironmentOverlayController(
            self.overlay._game, self, polling_allowed=connect_on_start)
        self.environment_overlay.set_opacity(self.overlay.element_opacity)
        self.queue.progress.connect(self.update_progress)
        self.make_overlay_controls()
        self.overlay_button.blockSignals(True)
        self.overlay_button.setChecked(self.overlay_toggle.isChecked())
        self.overlay_button.blockSignals(False)
        self.storage_panel = StorageSearchPanel(self.project_root); self.tabs.addTab(self.storage_panel, '창고')
        self.storage_panel.get_active_profile_id = lambda: self._active_profile_id
        self.music_status = QLabel(''); self.music_panel.layout().insertWidget(1, self.music_status)
        self.queue.changed.connect(lambda: self.music_status.setText(self.queue.current_label.text()))
        self.make_info_panel()
        self.toast = Toast(self)
        self.render_catalog()
        self.character_watcher = None
        self._active_profile_id = None
        self._character_manager_dialog = None
        self._owned_timer = QTimer(self)
        self._owned_timer.timeout.connect(self.refresh_owned_status)
        self._owned_timer.start(2000)
        if connect_on_start:
            self._try_connect()
            self.overlay.set_enabled(self.overlay_toggle.isChecked())
            self.environment_overlay.set_enabled(self.overlay_toggle.isChecked())
            self.character_watcher = CharacterWatcher(self.project_root, parent=self)
            self.character_watcher.profile_updated.connect(self._on_profile_updated)
            self.character_watcher.inventory_updated.connect(self.apply_owned_inventory)

    def _on_overlay_toggled(self, checked):
        self.toggle_overlay(checked)

    def _on_connection_result(self, ok, _detail):
        super()._on_connection_result(ok, _detail)
        if not ok: self.apply_owned_inventory(None)
        self.overlay.set_enabled(bool(ok) and self.overlay_toggle.isChecked())
        self.environment_overlay.set_enabled(bool(ok) and self.overlay_toggle.isChecked())

    def _on_profile_updated(self, profile, all_profiles):
        if self._active_profile_id != profile['profile_id']:
            self.gather_rows = None
            self.gather_status.setText('캐릭터가 변경되었습니다. 채집 목록을 다시 동기화해주세요.')
            self.render_catalog()
        self._active_profile_id = profile['profile_id']
        self.active_character_label.setText(character_profiles.display_name(profile))
        self.storage_panel.render_results()

    def apply_owned_inventory(self, profile):
        """Update cells only: polling must not reset selection, scroll or editors."""
        self.owned_items = OwnedItemsIndex.from_profile(profile)
        self._owned_checked_at = monotonic() if profile is not None else None
        self._owned_clock = datetime.now().strftime('%H:%M:%S') if profile is not None else ''
        self.refresh_owned_cells()
        self.refresh_owned_status()

    def refresh_owned_status(self):
        if self._owned_checked_at is None:
            status = '보유 수량 확인 전'
        elif monotonic() - self._owned_checked_at > 15:
            status = f'최근 확인 {self._owned_clock} · 재조회 대기'
        else:
            status = f'보유 수량 {self._owned_clock} 갱신'
        self.owned_status.setText(status + ' · 창고 = 캐릭터 창고 + 계정 창고')

    def refresh_owned_cells(self):
        if not self._owned_columns: return
        specs = {s.key: s for s in self.specs}
        equipment_names = {name for recipes in TOWN_EQUIPMENT.values() for name in recipes}
        was_blocked = self.catalog.blockSignals(True)
        for row in range(self.catalog.rowCount()):
            name_item = self.catalog.item(row, 0)
            spec = specs.get(name_item.data(Qt.UserRole)) if name_item else None
            if spec is None: continue
            name = spec_item_name(spec)
            unsupported = name in equipment_names
            counts = OwnedItemCounts() if unsupported else self.owned_items.for_name(name)
            fmt = lambda n: '—' if n is None else f'{n:,}'
            tooltip = ('게임 커넥터가 장비 보유 수량을 제공하지 않습니다.' if unsupported else
                       f'{name}\n소지: {fmt(counts.inventory)}개\n캐릭터 창고: {fmt(counts.character_storage)}개\n'
                       f'계정 창고: {fmt(counts.account_storage)}개\n합계: {fmt(counts.total)}개\n'
                       '현재 캐릭터 기준 · 다른 캐릭터의 소지품은 제외\n—: 수량 확인 전 / 확인 불가')
            for column, value in zip(self._owned_columns, (counts.inventory, counts.warehouse, counts.total)):
                item = self.catalog.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    item.setData(OWNED_COUNT_ROLE, True)
                    item.setForeground(QColor(OWNED_COUNT_COLOR))
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.catalog.setItem(row, column, item)
                item.setText(fmt(value))
                item.setToolTip(tooltip)
        self.catalog.blockSignals(was_blocked)

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
        if name in self.category_buttons: self.category_buttons[name].setChecked(True)
        self.category = name; self.render_catalog()

    def query_busy(self):
        storage_worker = getattr(getattr(self, 'storage_panel', None), '_refresh_worker', None)
        environment_worker = getattr(getattr(self, 'environment_overlay', None), 'worker', None)
        return any(w is not None and w.isRunning() for w in
                   (self.catalog_worker, self.info_worker, self._connection_worker,
                    self._scroll_worker, storage_worker, environment_worker))

    def _try_connect(self):
        if self.query_busy() or self.queue.worker or self.music_panel._current_title:
            self.toast.show_message('현재 요청이 끝난 뒤 연결을 확인해주세요.'); return
        super()._try_connect()

    def set_filter(self, name):
        self.filter_mode = name; self.render_catalog()

    def render_catalog(self, *_):
        self.catalog_note.setText('새 요리는 목표 수량 이상을 1회씩 제작합니다. 제작 호출마다 정령의 날개 5개가 소모되며, 별도 준비가 필요한 재료는 안내 후 멈춥니다.' if self.category == '요리' else '아이템을 오른쪽 대기열로 드래그한 뒤 시작하세요.')
        needle = self.search.text().strip().lower()
        if self.category == '제작':
            self.catalog_note.setText('목표 수량을 입력한 뒤 대기열로 드래그하세요. 필요한 가공을 채워두고, 생산 중에는 다른 부족 재료를 계속 준비합니다.')
        specs = [s for s in self.specs if kind(s) == self.category and needle in s.name.lower()]
        if self.category == '채집': specs.sort(key=lambda s: spec_item_name(s))
        if self.category == '제작':
            specs.sort(key=lambda s: catalogue_sort_key((spec_item_name(s), self.recipe_rows.get(spec_item_name(s),{}))))
        if self.filter_mode == '최근 사용': specs = sorted([s for s in specs if s.key in self.recent], key=lambda s: self.recent.index(s.key))
        self.catalog.blockSignals(True)
        headers = ['아이템', '목표 수량', '재료 상태'] if self.category == '제작' else ['재료 / 작업', '1회 기준', '채집 조건'] if self.category == '채집' else ['재료 / 작업', '1회 기준']
        self._owned_columns = tuple(range(len(headers), len(headers) + 3)) if self.category != '무한가공소' else ()
        if self._owned_columns: headers += ['소지', '창고', '합계']
        self.catalog.setColumnCount(len(headers))
        self.catalog.setHorizontalHeaderLabels(headers)
        self.catalog.setRowCount(0); self.catalog.setRowCount(len(specs))
        for i, spec in enumerate(specs):
            self.catalog.setRowHeight(i, 36)
            item = QTableWidgetItem(item_icon(spec_item_name(spec)), title(spec))
            item.setData(Qt.UserRole, spec.key)
            item.setToolTip('오른쪽 대기열로 드래그하여 추가')
            self.catalog.setItem(i, 0, item)
            if self.category == '제작':
                recipe = self.recipe_rows.get(spec_item_name(spec))
                produced = (recipe or {}).get('ProducedPerCraft', 1)
                step = produced if type(produced) is int and produced > 0 else 1
                spin = QSpinBox(); spin.setRange(1, 9999); spin.setFixedHeight(28)
                spin.setSingleStep(step)
                default = spec.target_count or (spec.make_worker().remaining if spec.key.startswith('equipment_') else 3)
                spin.setValue(self.catalog_counts.get(spec.key, max(1, default)))
                spin.setToolTip(f'최종 아이템 목표 수량 · 1회 {step}개 단위. 직접 입력하거나 위아래 화살표로 변경합니다.' if recipe and recipe.get('ProducedPerCraft') else '최종 아이템 목표 수량 · 게임에서 1회 생산량을 확인합니다.')
                spin.setKeyboardTracking(False)
                spin.valueChanged.connect(lambda n, k=spec.key: self.set_recipe_quantity(k, n))
                self.catalog.setCellWidget(i, 1, spin)
                self.catalog.setItem(i, 2, QTableWidgetItem(recipe_state(recipe) if recipe else '게임 연결 후 확인'))
                if recipe:
                    group = recipe.get('_catalog_group', '')
                    variants = recipe.get('_catalog_variants', [])
                    detail = '\n'.join(f"제작법 {n+1}: 1회 {v.get('ProducedPerCraft', '?')}개" for n,v in enumerate(variants)) if len(variants) > 1 else ''
                    item.setToolTip('\n'.join(part for part in [group, '오른쪽 대기열로 드래그하여 추가', detail] if part))
            else:
                self.catalog.setItem(i, 1, QTableWidgetItem('  ' + quantity(spec) + '  '))
                if self.category == '채집':
                    self.catalog.setItem(i, 2, QTableWidgetItem(gather_state(spec_item_name(spec), self.gather_rows)))
                    item.setToolTip('오른쪽 대기열로 드래그하여 추가\n목록에 없으면 미해금·숙련도 부족 또는 현재 미지원일 수 있습니다.\n실제 채집 조건은 게임에서 최종 확인합니다.')
        self.refresh_owned_cells()
        for col in self._owned_columns:
            self.catalog.horizontalHeaderItem(col).setToolTip('현재 캐릭터의 소지품 / 캐릭터·계정 창고 / 전체 합계\n수량에 마우스를 올리면 창고별 수량을 확인합니다.')
            self.catalog.horizontalHeaderItem(col).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.owned_status.setVisible(bool(self._owned_columns))
        self.catalog.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, self.catalog.columnCount()): self.catalog.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.catalog.blockSignals(False)
        self.empty.setText('검색 결과가 없습니다.' if not specs else '')
        self.empty.setVisible(not specs)
        self.equipment_buttons.setVisible(self.category == '제작')
        self.routine.setVisible(self.category == '무한가공소')
        self.craft_detail.setVisible(self.category == '제작' and isinstance(self.queue.worker, CraftingWorker))
        self.catalog_status.setVisible(self.category == '제작'); self.sync_button.setVisible(self.category == '제작')
        self.gather_status.setVisible(self.category == '채집'); self.gather_sync_button.setVisible(self.category == '채집')
        self.catalog.setMaximumHeight(125 if self.category == '무한가공소' else 16777215)

    def add_job_key(self, key):
        spec = next((s for s in self.specs if s.key == key), None)
        if spec is not None: self.add_job(spec)

    def add_job(self, spec, *, catalog_quantity=True):
        if catalog_quantity and spec.key.startswith(('craft:', 'equipment_')):
            name = spec_item_name(spec)
            default = spec.target_count or (spec.make_worker().remaining if spec.key.startswith('equipment_') else 3)
            amount = self.catalog_counts.get(spec.key, default)
            spec = replace(spec, name=f'제작: {name}', target_count=amount, recipe_name=name,
                           make_worker=lambda r=name, n=amount: CraftingWorker(r, n))
        elif spec.key.startswith('equipment_'):
            # Weekly scroll batches retain their own worker and exact 6/10/5
            # target. Their hidden key suffix must never become a recipe name.
            spec = replace(spec, recipe_name=spec.make_worker().recipe)
        self.queue.add(spec)
        self.recent = [spec.key] + [k for k in self.recent if k != spec.key]
        self.settings.setValue('recent', self.recent[:30])
        self.toast.show_message(f'대기열에 추가됨 · {title(spec)}')

    def set_recipe_quantity(self, key, amount):
        self.catalog_counts[key] = amount
        self.show_recipe_detail()

    def sync_gathering(self):
        if self.query_busy(): return
        if self.queue.worker or self.music_panel._current_title:
            self.toast.show_message('현재 작업이 끝난 뒤 채집 목록을 동기화해주세요.'); return
        self.gather_status.setText('게임의 채집 목록을 읽는 중…')
        self.gather_sync_button.setEnabled(False)
        self.catalog_worker = GatherCatalogWorker(self)
        self.catalog_worker.result.connect(self.apply_gathering)
        self.catalog_worker.finished.connect(lambda: self.gather_sync_button.setEnabled(True))
        self.catalog_worker.start()

    def apply_gathering(self, data):
        try: rows = parse_gather_items(data)
        except ValueError as exc:
            self.gather_status.setText(str(exc)); return
        self.gather_rows = rows
        existing = {s.key for s in self.specs}
        for name in sorted(rows):
            key = 'gather_' + name
            if key not in existing:
                self.specs.append(JobSpec(key, f'채집: {name} x100', lambda n=name: GatherJobWorker(n)))
        total = sum(s.key.startswith('gather_') for s in self.specs)
        self.gather_status.setText(f'채집 {total}종 · 현재 캐릭터 목록 {len(rows)}종 · 미해금 항목도 참고 목록에 유지됩니다.')
        self.render_catalog()

    def sync_recipes(self):
        if self.query_busy(): return
        if self.queue.worker or self.music_panel._current_title:
            self.toast.show_message('현재 작업을 일시정지한 뒤 목록을 동기화해주세요.'); return
        self.catalog_status.setText('게임의 전체 제작 목록을 읽는 중…'); self.sync_button.setEnabled(False)
        self.catalog_worker = RecipeCatalogWorker(self)
        self.catalog_worker.result.connect(self.apply_recipes)
        self.catalog_worker.finished.connect(lambda: self.sync_button.setEnabled(True))
        self.catalog_worker.start()

    def apply_recipes(self, data):
        try: live = parse_recipes(data)
        except ValueError as exc:
            self.catalog_status.setText(str(exc)); return
        rows = merge_reference_recipes(live)
        self.recipe_rows = rows; self.catalog_loaded = True
        self.specs = [s for s in self.specs if not s.key.startswith(('craft:', 'equipment_'))]
        for name, row in sorted(rows.items(), key=catalogue_sort_key):
            produced = row.get('ProducedPerCraft', 1)
            default = produced if isinstance(produced, int) and produced > 0 else 1
            key = 'craft:' + name
            self.specs.append(JobSpec(key, '제작: ' + name, lambda r=name, n=default: CraftingWorker(r, n), default, name))
        variants = sum(row.get('_catalog_variant_count',1) for row in live.values())
        self.catalog_status.setText(f'등록 아이템 {len(rows)}종 · 게임 확인 {len(live)}종 / 제작법 {variants}개')
        self.render_catalog()

    def show_recipe_detail(self):
        if self.category != '제작' or self.queue.worker: return
        index = self.catalog.currentRow()
        if index < 0: return
        item = self.catalog.item(index, 0)
        if not item: return
        spec = next((s for s in self.specs if s.key == item.data(Qt.UserRole)), None)
        if not spec: return
        recipe = self.recipe_rows.get(spec_item_name(spec), {})
        self.craft_detail.show()
        rows = [{'name': m.get('DisplayName',''), 'owned': m.get('Owned',0), 'required': m.get('Required',0), 'state':'준비 필요'} for m in recipe.get('MissingIngredients', [])]
        message = '현재 부족한 1회분 재료입니다. 확인된 재료는 목표 수량만큼 준비하고 매 제작 전에 다시 확인합니다.' if rows else '실행 시 재료와 생산시설을 다시 확인합니다.'
        if recipe.get('_catalog_reference_only'):
            message = '제작 조건 확인 전입니다. 제작 목록을 동기화하면 게임의 실제 재료와 생산량을 확인합니다.'
        elif recipe.get('_catalog_variant_count', 1) > 1:
            outputs = ' / '.join(str(v.get('ProducedPerCraft','?')) + '개' for v in recipe['_catalog_variants'])
            message = f'동명 제작법 {recipe["_catalog_variant_count"]}종 (1회 {outputs}). 제작 가능 여부와 재료 준비량을 비교해 자동 선택합니다. 게임에는 이름으로 제작을 요청하며 실제 생산 결과를 확인합니다.'
        self.craft_detail.show_progress({'recipe':spec_item_name(spec), 'target':self.catalog_counts.get(spec.key, spec.target_count or 3),
           'completed':0, 'stage':'준비 계획', 'materials':rows,
           'message':message})

    def update_progress(self, data):
        self.overlay.set_progress(data)
        self.craft_detail.show_progress(data)
        if self.category == '제작': self.craft_detail.show()

    def make_overlay_controls(self):
        group = QFrame(); form = QVBoxLayout(group); form.setContentsMargins(8, 8, 8, 8)
        line = QHBoxLayout(); self.overlay_toggle = QCheckBox('게임 위 진행 표시 · 80% 크기')
        self.overlay_toggle.setChecked(self.settings.value('overlay/ui_enabled', True, type=bool))
        line.addWidget(self.overlay_toggle); form.addLayout(line)
        options = QHBoxLayout(); self.overlay_lock = QCheckBox('위치 잠금'); self.overlay_click = QCheckBox('게임 클릭 통과')
        self.overlay_lock.setChecked(self.overlay.locked); self.overlay_click.setChecked(self.overlay.click_through)
        options.addWidget(self.overlay_lock); options.addWidget(self.overlay_click); form.addLayout(options)
        line2 = QHBoxLayout(); line2.addWidget(QLabel('표시 불투명도'))
        self.overlay_opacity = QSlider(Qt.Horizontal); self.overlay_opacity.setRange(30,100); self.overlay_opacity.setValue(round(self.overlay.element_opacity*100))
        line2.addWidget(self.overlay_opacity); form.addLayout(line2)
        self.overlay_toggle.toggled.connect(self.toggle_overlay)
        self.overlay_lock.toggled.connect(self.overlay.set_locked)
        self.overlay_click.toggled.connect(self.overlay.set_click_through)
        self.overlay_opacity.valueChanged.connect(lambda v:self.overlay.set_opacity(v/100))
        self.overlay_opacity.valueChanged.connect(lambda v:self.environment_overlay.set_opacity(v/100))
        preview = button('위치 미리보기', lambda: self.overlay.set_preview(not self.overlay._preview))
        preview.setToolTip('게임 연결 없이 오버레이 위치를 확인합니다. 위치 잠금을 해제하면 끌어 옮길 수 있습니다.')
        form.addWidget(preview)
        self.queue.layout().insertWidget(self.queue.layout().count()-2, group)

    def toggle_overlay(self, enabled):
        self.settings.setValue('overlay/ui_enabled', enabled)
        self.overlay.set_enabled(enabled)
        self.environment_overlay.set_enabled(enabled)
        for control in (self.overlay_toggle, self.overlay_button):
            control.blockSignals(True)
            control.setChecked(enabled)
            control.blockSignals(False)

    def add_weekly_equipment(self, town, weeks):
        """'주간 제작(마을)'/'x5' buttons - queue that town's 3 scroll recipes at once.

        임무 게시판은 같은 스크롤을 한 주에 최대 3개까지 팔아서(user, 2026-09-20), 한 주 몫은
        3 x 2(스크롤 하나당 장비 2개) = 6개 - 그래서 x2 카탈로그 잡이 아니라 숨은 x6 잡
        (EQUIPMENT_WEEKLY_X6)을 쓴다. x5 버튼은 목표 15개를 새 x15 잡을 따로 만드는 대신
        기존 x10 잡 + 새 x5 잡을 같이 큐에 넣어서 채운다(10+5=15, user 지정)."""
        for recipe in TOWN_EQUIPMENT[town]:
            if weeks == 5:
                self.add_job(EQUIPMENT_WEEKLY_X10[recipe], catalog_quantity=False)
                self.add_job(EQUIPMENT_WEEKLY_X5[recipe], catalog_quantity=False)
            else:
                self.add_job(EQUIPMENT_WEEKLY_X6[recipe], catalog_quantity=False)

    def _find_equipment_spec(self, recipe_name):
        """Match a scroll-derived recipe name to a catalog spec, tolerant of whitespace
        differences - the live API is known to be inconsistent about spacing within an
        item name (recipe_info() already normalizes for the same reason when matching
        get_craftable_items)."""
        target = ''.join(recipe_name.split()).casefold()
        # The live crafting catalogue replaces browsing equipment rows. Scroll
        # actions must still resolve their known two-item equipment workers.
        for s in JOB_CATALOG:
            if s.key.startswith('equipment_') and ''.join(s.key[len('equipment_'):].split()).casefold() == target:
                return s
        return None

    def craft_all_owned_scrolls(self):
        """'보유 스크롤 모두 진행' - 인벤토리의 "제작 스크롤: <이름>"을 전부 확인해서, 아는
        레시피(EQUIPMENT_RECIPES)면 그 개수만큼 반복(◀N▶)으로 대기열에 추가한다. 스크롤은
        창고(캐릭터창고/계정창고)엔 보관이 안 되는 아이템이라 인벤토리만 본다. 모르는
        스크롤(아직 JOB으로 안 만든 다른 제작 종류)은 조용히 건너뛴다(user, 2026-09-20)."""
        if self.query_busy() or self.queue.worker or self.music_panel._current_title:
            self.toast.show_message('현재 요청이 끝난 뒤 스크롤을 확인해주세요.')
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
        if self.query_busy(): return
        if self.queue.worker or self.music_panel._current_title:
            self.toast.show_message('현재 작업이 끝난 뒤 정보를 새로고침해주세요.'); return
        self.info_worker = InfoWorker(self); self.info_worker.result.connect(self.update_info)
        self.info_worker.finished.connect(self.finish_refresh); self.info_worker.start()

    def finish_refresh(self):
        if self.queue.worker or self.music_panel._current_title or self.query_busy(): return
        self.music_panel.refresh_songs()
        self.sync_recipes()

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
        # Stop new environment reads before checking the in-flight request.
        self.environment_overlay.set_enabled(False)
        workers = [self.queue.worker, self._connection_worker, self.info_worker,
                   self.catalog_worker, self._scroll_worker, self.storage_panel._refresh_worker,
                   self.environment_overlay.worker]
        if any(w is not None and w.isRunning() for w in workers):
            self.queue.paused = True
            if self.queue.worker:
                self.queue.interrupted = True
                self.queue.worker.request_stop()
            self.toast.show_message('실행 중인 요청이 끝난 뒤 다시 닫아주세요.', 4000)
            self.queue.render(); event.ignore(); return
        if self.music_panel._current_title:
            self.music_panel._stop_playback()
        self.overlay.set_enabled(False); self.overlay.close()
        self.environment_overlay.close()
        if self.character_watcher is not None:
            self.character_watcher.stop()
            watcher_workers = (self.character_watcher._poll_worker, self.character_watcher._identify_worker)
            if any(w is not None and w.isRunning() for w in watcher_workers):
                self.toast.show_message('캐릭터 정보 조회가 끝난 뒤 다시 닫아주세요.', 4000)
                event.ignore(); return
        self.routine.close(); event.accept()
