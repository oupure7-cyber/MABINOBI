from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView
from .item_icons import item_icon

class CraftingDetail(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 8, 0, 0); layout.setSpacing(5)
        self.title = QLabel('아이템을 선택하면 재료 상태가 표시됩니다.')
        self.stage = QLabel('시설 생산 중에도 부족한 재료 준비'); self.stage.setStyleSheet('color: #9fb3bd;')
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['재료', '보유 / 필요', '준비 상태'])
        self.table.verticalHeader().hide(); self.table.setShowGrid(False)
        self.table.setIconSize(QSize(22,22)); self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.note = QLabel('필요한 만큼 가공을 등록하고, 생산 중에는 남은 채집을 이어갑니다.'); self.note.setWordWrap(True)
        layout.addWidget(self.title); layout.addWidget(self.stage); layout.addWidget(self.table, 1); layout.addWidget(self.note)
        self.setMinimumHeight(155); self.setMaximumHeight(250)

    def show_progress(self, data):
        self.title.setText(str(data.get('recipe', '제작 준비')))
        self.stage.setText(f"{data.get('stage', '대기')}  ·  완성 {data.get('completed', 0)} / {data.get('target', 0)}개")
        self.note.setText(str(data.get('message') or '재료 확보 → 생산시설 가공 → 최종 제작'))
        rows = data.get('materials', [])
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            self.table.setRowHeight(index, 30)
            name = str(row.get('name', ''))
            self.table.setItem(index, 0, QTableWidgetItem(item_icon(name), name))
            self.table.setItem(index, 1, QTableWidgetItem(f"{row.get('owned', 0)} / {row.get('required', 0)}"))
            self.table.setItem(index, 2, QTableWidgetItem(str(row.get('state', '확인 중'))))
