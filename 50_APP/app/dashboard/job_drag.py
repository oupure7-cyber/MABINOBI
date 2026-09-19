"""Only accept local catalog drags; arbitrary text/files never execute jobs."""
from PySide6.QtCore import Qt, QMimeData, Signal
from PySide6.QtWidgets import QTableWidget, QAbstractItemView

JOB_MIME = 'application/x-mabinobi-job-key'

class JobCatalogTable(QTableWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def mimeTypes(self): return [JOB_MIME]

    def mimeData(self, items):
        mime = QMimeData()
        if items:
            item = self.item(items[0].row(), 0)
            if item and item.data(Qt.UserRole):
                mime.setData(JOB_MIME, item.data(Qt.UserRole).encode('utf-8'))
        return mime

    def supportedDropActions(self): return Qt.CopyAction

class JobDropTable(QTableWidget):
    jobDropped = Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDropIndicatorShown(True)

    def valid_key(self, event):
        source = event.source()
        if not isinstance(source, JobCatalogTable) or not event.mimeData().hasFormat(JOB_MIME):
            return None
        try: key = bytes(event.mimeData().data(JOB_MIME)).decode('utf-8')
        except UnicodeDecodeError: return None
        # The dragged key must still exist in this catalog, not an external MIME payload.
        for row in range(source.rowCount()):
            item = source.item(row, 0)
            if item and item.data(Qt.UserRole) == key: return key
        return None

    def dragEnterEvent(self, event):
        if self.valid_key(event):
            event.setDropAction(Qt.CopyAction); event.accept()
        else: event.ignore()

    def dragMoveEvent(self, event): self.dragEnterEvent(event)

    def dropEvent(self, event):
        key = self.valid_key(event)
        if key:
            self.jobDropped.emit(key)
            event.setDropAction(Qt.CopyAction); event.accept()
        else: event.ignore()
