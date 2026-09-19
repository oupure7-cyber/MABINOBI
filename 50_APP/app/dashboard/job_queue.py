"""Right-side JOB queue column (user-specified, 2026-09-18): runs a finite ordered list of
JOBs one after another. A JOB is "a finite set of actions" - the existing infinite 가공 무한
routine becomes a JOB the moment it's given an end condition (here, a time limit), which is
exactly what AlteringRoutineWorker's `duration_seconds` (see altering_routine.py) was added
for. Any future JOB type just needs to expose the same shape: a QThread-like worker with
`status`/`blocked`/`stopped` signals and a `request_stop()` method - register it in
JOB_CATALOG and it shows up in the searchable catalog at the bottom of the column for free.
"요리: 야채 볶음 x10"/"요리: 야채 볶음 x50" are a second, different JOB shape (food_crafting_job.py,
FoodCraftWorker): gather whatever raw ingredients are short, then execute_crafting the target
count once and finish - a one-shot worker rather than a repeating routine.

A third, even simpler shape (gather_job.py, GatherJobWorker) replaces the old always-visible
채집 바로가기 button grid (removed from gather_panel.py 2026-09-18): one execute_gathering call
for a fixed item, named "채집: <이름> x100" (the queue's own ◀ N ▶ stepper covers repeating it
past one 100-item call, same as every other JOB here).

Layout: a "현재 작업" header, a single QListWidget showing the running job (row 0, if any,
highlighted) followed by pending jobs, a trash drop zone, then a search box + catalog list
(mirrors music_panel.py's song search) at the bottom.

Each row shows its name plus a `◀ N ▶` stepper (1-9) for how many times to repeat that JOB
before moving on. The running job's stepper decrements by itself as repeats complete.

Drag and drop (deliberately narrow, see below): dragging a row (running or pending) onto the
trash deletes it - dragging the *running* row aborts it and immediately advances to the next
JOB. Dragging a catalog entry onto the queue appends a new instance of it to the end.
Reordering pending jobs via drag is NOT implemented - QListWidget's built-in internal-move
drag reordering is well known to desync from setItemWidget() rows (the widget is bound to a
row index, not to the item object, so Qt's own move can leave the wrong widget on a row), and
avoiding that entirely (by only ever accepting drops that originate from the catalog) was the
simplest way to sidestep the whole class of bug rather than working around it.

Runs at most one JOB's worker at a time, and defers starting a new one while the manual "가공
무한" button in gather_panel.py has its own worker running (checked via GatherPanel.is_busy(),
wired up in main_window.py) - same one-CLI-caller-at-a-time constraint as everywhere else in
this app.

If a JOB's worker reports `blocked` (a popup needs the user), the whole queue pauses rather
than silently marking that repeat "done" and moving on - the same "don't loop through it"
safeguard the single-job routine already has, just extended to not skip past it at the queue
level either. A 재개 (resume) button appears to retry the same JOB once the user has cleared
whatever needed attention in-game.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .altering_routine import AlteringRoutineWorker
from .food_crafting_job import FoodCraftWorker, Ingredient
from .recipe_cooking import RECIPES, RecipeCookingWorker
from .equipment_crafting import EQUIPMENT_RECIPES, EquipmentCraftWorker
from .gather_job import GATHER_ITEMS, GatherJobWorker

MIN_REPEATS = 1
MAX_REPEATS = 9
BUSY_RECHECK_MS = 3000  # how often to retry starting a job while gather_panel's own routine runs


@dataclass(frozen=True)
class JobSpec:
    """One entry in the searchable job catalog - a named, instantiable job type."""

    key: str
    name: str
    make_worker: Callable[[], object]  # -> a QThread-like: .status/.blocked/.stopped, .request_stop()


def _make_altering_1h() -> AlteringRoutineWorker:
    return AlteringRoutineWorker(duration_seconds=3600)


# 야채볶음 10개 기준 재료(사용자 지정, 2026-09-18): 감자 80/양파 30/양배추 60/허브 20.
# 50개는 그 5배 - 같은 레시피니 배율만 다르다.
def _make_veggie_stir_fry(craft_count: int, scale: int) -> FoodCraftWorker:
    return FoodCraftWorker(
        recipe="야채볶음",
        craft_count=craft_count,
        ingredients=(
            Ingredient("감자", 80 * scale),
            Ingredient("양파", 30 * scale),
            Ingredient("양배추", 60 * scale),
            Ingredient("허브", 20 * scale),
        ),
    )


def _make_veggie_stir_fry_10() -> FoodCraftWorker:
    return _make_veggie_stir_fry(10, 1)


def _make_veggie_stir_fry_50() -> FoodCraftWorker:
    return _make_veggie_stir_fry(50, 5)


def _make_gather_job(display_name: str) -> Callable[[], GatherJobWorker]:
    # A factory-returning-factory, not a bare lambda in the loop below - closes over
    # `display_name` by value so every entry doesn't end up capturing the loop's last item.
    def factory() -> GatherJobWorker:
        return GatherJobWorker(display_name)

    return factory


JOB_CATALOG: list[JobSpec] = [
    JobSpec(key="altering_1h", name="가공무한 1시간", make_worker=_make_altering_1h),
    JobSpec(key="veggie_stir_fry_10", name="요리: 야채 볶음 x10", make_worker=_make_veggie_stir_fry_10),
    JobSpec(key="veggie_stir_fry_50", name="요리: 야채 볶음 x50", make_worker=_make_veggie_stir_fry_50),
]
JOB_CATALOG.extend(
    JobSpec(key=f"gather_{item}", name=f"채집: {item} x100", make_worker=_make_gather_job(item))
    for item in GATHER_ITEMS
)
JOB_CATALOG.extend(
    JobSpec(key=f'cooking_{recipe}_{count}', name=f'요리: {recipe} x{count}',
            make_worker=lambda r=recipe, n=count: RecipeCookingWorker(r, n))
    for recipe in RECIPES for count in (10, 50)
)
JOB_CATALOG.extend(
    JobSpec(key=f'equipment_{recipe}', name=f'제작: {recipe} x2',
            make_worker=lambda r=recipe: EquipmentCraftWorker(r))
    for recipe in EQUIPMENT_RECIPES
)
JOB_CATALOG_BY_KEY: dict[str, JobSpec] = {spec.key: spec for spec in JOB_CATALOG}


@dataclass
class QueuedJob:
    """One item sitting in the queue (or currently running). `repeats` counts down."""

    spec: JobSpec
    repeats: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


class RepeatStepper(QWidget):
    """The `◀ N ▶` control. Mutates the QueuedJob it was given directly (same object the
    panel's own bookkeeping holds), so no round-trip is needed for a plain repeat-count edit."""

    def __init__(self, job: QueuedJob, parent=None):
        super().__init__(parent)
        self._job = job
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        dec = QPushButton("◀")
        dec.setFixedWidth(22)
        dec.clicked.connect(lambda: self._bump(-1))
        row.addWidget(dec)

        self._count_label = QLabel(str(job.repeats))
        self._count_label.setFixedWidth(14)
        self._count_label.setAlignment(Qt.AlignCenter)
        row.addWidget(self._count_label)

        inc = QPushButton("▶")
        inc.setFixedWidth(22)
        inc.clicked.connect(lambda: self._bump(1))
        row.addWidget(inc)

    def _bump(self, delta: int) -> None:
        self._job.repeats = max(MIN_REPEATS, min(MAX_REPEATS, self._job.repeats + delta))
        self._count_label.setText(str(self._job.repeats))

    def refresh(self) -> None:
        self._count_label.setText(str(self._job.repeats))


class JobRowWidget(QWidget):
    """One queue row: name + RepeatStepper. `running=True` highlights it as the current job."""

    def __init__(self, job: QueuedJob, *, running: bool, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 4, 6, 4)

        prefix = "▶ " if running else ""
        name_label = QLabel(f"{prefix}{job.spec.name}")
        name_label.setWordWrap(True)
        if running:
            name_label.setStyleSheet("font-weight: 700; color: #f0c060;")
        row.addWidget(name_label, 1)

        self.stepper = RepeatStepper(job)
        row.addWidget(self.stepper)

        if running:
            self.setStyleSheet("background-color: #3a2f1a; border-radius: 4px;")


class JobCatalogList(QListWidget):
    """Bottom of the column: searchable list of implemented job types - drag source only."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)


class JobQueueListWidget(QListWidget):
    """The combined running+pending list. Only ever accepts drops that originate from a
    JobCatalogList (appended to the end) - see module docstring for why internal reordering
    isn't supported. Its own rows can still be dragged *out* to the trash."""

    def __init__(self, panel: "JobQueuePanel", parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self._drag_item: QListWidgetItem | None = None

    def startDrag(self, supported_actions) -> None:  # noqa: N802 - Qt override
        self._drag_item = self.currentItem()
        super().startDrag(supported_actions)

    def take_dragged_item(self) -> QListWidgetItem | None:
        item = self._drag_item
        self._drag_item = None
        return item

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if isinstance(event.source(), JobCatalogList):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if isinstance(event.source(), JobCatalogList):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        source = event.source()
        if isinstance(source, JobCatalogList):
            item = source.currentItem()
            if item is not None:
                self._panel.enqueue_from_catalog(item.data(Qt.UserRole))
            event.acceptProposedAction()
        else:
            event.ignore()


class JobTrashZone(QLabel):
    """Drop a queue row here to delete it (aborts it first if it was the running job)."""

    def __init__(self, queue: JobQueueListWidget, panel: "JobQueuePanel", parent=None):
        super().__init__("🗑", parent)
        self._queue = queue
        self._panel = panel
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(36)
        self.setStyleSheet(
            "QLabel { background-color: #2b2b30; border: 2px dashed #555; border-radius: 8px;"
            " font-size: 16px; }"
        )

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.source() is self._queue:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        item = self._queue.take_dragged_item()
        if item is not None:
            self._panel.delete_job(item.data(Qt.UserRole))
        event.acceptProposedAction()


class JobQueuePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._jobs: dict[str, QueuedJob] = {}
        self._pending: list[QueuedJob] = []
        self._current: QueuedJob | None = None
        self._current_worker: AlteringRoutineWorker | None = None
        self._aborted_by_user = False
        self._paused_due_to_block = False
        self._gather_panel = None  # set via set_gather_panel() - avoids a circular import

        outer = QVBoxLayout(self)

        header_row = QHBoxLayout()
        self._current_label = QLabel("현재 작업: 없음")
        self._current_label.setWordWrap(True)
        self._current_label.setStyleSheet("font-weight: 700; font-size: 13px;")
        header_row.addWidget(self._current_label, 1)
        self._resume_btn = QPushButton("▶ 재개")
        self._resume_btn.setEnabled(False)
        self._resume_btn.clicked.connect(self._resume_after_block)
        header_row.addWidget(self._resume_btn)
        outer.addLayout(header_row)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color: #aaa; font-size: 11px;")
        outer.addWidget(self._status_label)

        self._list = JobQueueListWidget(self)
        outer.addWidget(self._list, 1)

        outer.addWidget(JobTrashZone(self._list, self))

        outer.addWidget(QLabel("JOB 검색"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("JOB 이름 검색")
        self._search.textChanged.connect(self._apply_filter)
        outer.addWidget(self._search)

        self._catalog = JobCatalogList()
        self._catalog.itemDoubleClicked.connect(lambda item: self.enqueue_from_catalog(item.data(Qt.UserRole)))
        self._catalog.setMaximumHeight(140)
        outer.addWidget(self._catalog)
        self._apply_filter("")

        self._busy_retry_timer = QTimer(self)
        self._busy_retry_timer.setInterval(BUSY_RECHECK_MS)
        self._busy_retry_timer.timeout.connect(self._maybe_start_next)

        self._render()

    def set_gather_panel(self, gather_panel) -> None:
        self._gather_panel = gather_panel

    def is_running(self) -> bool:
        return self._current_worker is not None

    # -- catalog / search ----------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        self._catalog.clear()
        needle = text.strip().lower()
        for spec in JOB_CATALOG:
            if needle in spec.name.lower():
                item = QListWidgetItem(spec.name)
                item.setData(Qt.UserRole, spec.key)
                self._catalog.addItem(item)

    def enqueue_from_catalog(self, spec_key: str) -> None:
        spec = JOB_CATALOG_BY_KEY.get(spec_key)
        if spec is None:
            return
        job = QueuedJob(spec=spec, repeats=MIN_REPEATS)
        self._jobs[job.id] = job
        self._pending.append(job)
        self._render()
        self._maybe_start_next()

    # -- rendering -------------------------------------------------------------

    def _render(self) -> None:
        self._list.clear()
        rows = ([self._current] if self._current else []) + self._pending
        for job in rows:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, job.id)
            self._list.addItem(item)
            widget = JobRowWidget(job, running=(job is self._current))
            item.setSizeHint(widget.sizeHint())
            self._list.setItemWidget(item, widget)

        if self._paused_due_to_block:
            self._current_label.setText(f"⚠️ 일시정지됨: {self._current.spec.name if self._current else '-'}")
            self._current_label.setStyleSheet("font-weight: 700; font-size: 13px; color: #ff5555;")
        else:
            self._current_label.setText(f"현재 작업: {self._current.spec.name}" if self._current else "현재 작업: 없음")
            self._current_label.setStyleSheet("font-weight: 700; font-size: 13px;")
        self._resume_btn.setEnabled(self._paused_due_to_block)

    # -- lifecycle -------------------------------------------------------------

    def delete_job(self, job_id: str) -> None:
        if self._current is not None and self._current.id == job_id:
            self._abort_current()
            return
        job = self._jobs.pop(job_id, None)
        if job is None:
            return
        self._pending = [j for j in self._pending if j.id != job_id]
        self._render()

    def _abort_current(self) -> None:
        if self._current_worker is None:
            # nothing actually running (shouldn't normally happen) - just drop it
            if self._current is not None:
                self._jobs.pop(self._current.id, None)
                self._current = None
            self._render()
            self._maybe_start_next()
            return
        self._aborted_by_user = True
        self._status_label.setText(f"⏹ '{self._current.spec.name}' 중단 요청 - 다음 JOB으로 넘어갑니다")
        self._current_worker.request_stop()

    def _resume_after_block(self) -> None:
        self._paused_due_to_block = False
        self._render()
        self._maybe_start_next()

    def _maybe_start_next(self) -> None:
        # `self._current` staying set with no worker attached means its last repeat just
        # finished and more remain (see _on_worker_stopped) - that case must still (re)start a
        # fresh worker for the SAME job, so the guard here is on the worker, not on `_current`.
        if self._paused_due_to_block or self._current_worker is not None:
            return
        if self._gather_panel is not None and self._gather_panel.is_busy():
            self._status_label.setText("⏳ 채집/가공 무한 버튼이 사용 중이라 대기 중...")
            if not self._busy_retry_timer.isActive():
                self._busy_retry_timer.start()
            return
        self._busy_retry_timer.stop()

        if self._current is None:
            if not self._pending:
                return
            self._current = self._pending.pop(0)

        self._render()
        worker = self._current.spec.make_worker()
        worker.status.connect(self._on_worker_status)
        worker.blocked.connect(self._on_worker_blocked)
        worker.stopped.connect(self._on_worker_stopped)
        self._current_worker = worker
        worker.start()

    def _on_worker_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _on_worker_blocked(self, kind: str) -> None:
        self._paused_due_to_block = True
        self._status_label.setText(f"⚠️ 게임 확인 필요: {kind}")
        self._render()

    def _on_worker_stopped(self) -> None:
        self._current_worker = None
        aborted = self._aborted_by_user
        self._aborted_by_user = False

        if self._paused_due_to_block:
            self._render()
            return  # don't decrement/advance - wait for 재개

        if aborted or self._current is None:
            if self._current is not None:
                self._jobs.pop(self._current.id, None)
            self._current = None
            self._render()
            self._maybe_start_next()
            return

        self._current.repeats -= 1
        if self._current.repeats <= 0:
            self._jobs.pop(self._current.id, None)
            self._current = None
        self._render()
        self._maybe_start_next()
