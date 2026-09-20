"""Transparent, non-activating progress above the foreground game window."""
from __future__ import annotations
import math
import os
import sys
from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QApplication, QWidget
from .item_icons import item_icon

SCALE = .8
NOMINAL_SIZE = (300, 330)

def _number(value, default=0):
    try:
        value = float(value)
        return max(0, value) if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default

def _count(value):
    value = _number(value)
    return f'{int(value):,}' if value == int(value) else f'{value:,.1f}'

def _time(value):
    minutes, seconds = divmod(int(_number(value)), 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}시간 {minutes}분' if hours else f'{minutes:02d}:{seconds:02d}'

def _truth(value):
    return str(value).lower() not in ('false', '0', 'no', 'off', '', 'none')

class _GameWindow:
    """Read public Win32 metadata only; no hooks, injection, or game input."""
    def __init__(self):
        self.hwnd = None
        self.available = sys.platform == 'win32'
        if not self.available: return
        import ctypes
        from ctypes import wintypes
        self.c, self.w = ctypes, wintypes
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user.GetForegroundWindow.restype = wintypes.HWND
        for name in ('IsWindow', 'IsWindowVisible', 'IsIconic'):
            getattr(self.user, name).argtypes = [wintypes.HWND]
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback_type, wintypes.LPARAM]

    def _pid(self, hwnd):
        pid = self.w.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, self.c.byref(pid))
        return pid.value

    def _is_game(self, hwnd):
        if not self.user.IsWindowVisible(hwnd) or self.user.IsIconic(hwnd): return False
        handle = self.kernel.OpenProcess(0x1000, False, self._pid(hwnd))
        if not handle: return False
        try:
            path = self.c.create_unicode_buffer(32768)
            length = self.w.DWORD(len(path))
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, path, self.c.byref(length)): return False
            filename = path.value.replace('\\', '/').rsplit('/', 1)[-1].lower()
            return filename in ('mabinogimobile.exe', 'mabinogimobile-win64-shipping.exe')
        finally:
            self.kernel.CloseHandle(handle)

    def _find(self):
        found = []
        @self.callback_type
        def inspect(hwnd, _):
            if self._is_game(hwnd):
                found.append(hwnd)
                return False
            return True
        self.user.EnumWindows(inspect, 0)
        return found[0] if found else None

    def rectangle(self, allow_app=False):
        if not self.available: return None
        foreground = self.user.GetForegroundWindow()
        if not foreground: return None
        if self._is_game(foreground): self.hwnd = foreground
        elif not (allow_app and self._pid(foreground) == os.getpid()): return None
        if not self.hwnd or not self.user.IsWindow(self.hwnd) or self.user.IsIconic(self.hwnd):
            self.hwnd = self._find() if allow_app else None
        if not self.hwnd: return None
        rect, origin = self.w.RECT(), self.w.POINT()
        if not self.user.GetClientRect(self.hwnd, self.c.byref(rect)): return None
        if not self.user.ClientToScreen(self.hwnd, self.c.byref(origin)): return None
        if rect.right < 100 or rect.bottom < 100: return None
        # Qt positions screen origins logically; native sizes need DPI conversion.
        app = QApplication.instance()
        screen = app.primaryScreen()
        for candidate in app.screens():
            geo, ratio = candidate.geometry(), candidate.devicePixelRatio()
            if geo.x() <= origin.x < geo.x() + geo.width() * ratio and geo.y() <= origin.y < geo.y() + geo.height() * ratio:
                screen = candidate
                break
        geo, ratio = screen.geometry(), screen.devicePixelRatio()
        return QRectF(geo.x() + (origin.x - geo.x()) / ratio,
                      geo.y() + (origin.y - geo.y()) / ratio,
                      rect.right / ratio, rect.bottom / ratio)

class ProgressOverlay(QWidget):
    """80% display. All setters run on GUI thread. Settings: QSettings or dict.

    set_preview(True) bypasses foreground detection for a deliberate preview.
    Unlocking temporarily disables click-through so the overlay can be dragged.
    """
    def __init__(self, settings=None, parent=None):
        # Independent native window: minimizing the dashboard must not hide it.
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        if parent is not None:
            parent.destroyed.connect(self.deleteLater)
        self.settings = settings
        self.enabled = _truth(self._read('enabled', True))
        self.locked = _truth(self._read('locked', True))
        self.click_through = _truth(self._read('click_through', True))
        self.element_opacity = max(.2, min(1., _number(self._read('opacity', .95), .95)))
        self._offset = None
        raw = self._read('position', None)
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            try: self._offset = QPoint(int(raw[0]), int(raw[1]))
            except (TypeError, ValueError): pass
        self._preview = False
        self._drag = None
        self._game_rect = None
        self._game = _GameWindow()
        self.payload = {}
        self.setWindowTitle('마비노비 제작 현황')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # The dashboard's QWidget stylesheet must not become a backplate here.
        self.setStyleSheet('background: transparent; border: none;')
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(round(NOMINAL_SIZE[0] * SCALE), round(NOMINAL_SIZE[1] * SCALE))
        self._apply_input_flags()
        self._timer = QTimer(self)
        self._timer.setInterval(600)
        self._timer.timeout.connect(self._sync_visibility)
        self._timer.start()

    def _read(self, key, default):
        if self.settings is None: return default
        if hasattr(self.settings, 'value'): return self.settings.value('overlay/' + key, default)
        return self.settings.get('overlay/' + key, default)

    def _write(self, key, value):
        if self.settings is None: return
        if hasattr(self.settings, 'setValue'): self.settings.setValue('overlay/' + key, value)
        else: self.settings['overlay/' + key] = value

    def set_progress(self, payload):
        self.payload = dict(payload or {})
        self.update()
        self._sync_visibility()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self._write('enabled', self.enabled)
        self._sync_visibility()

    def set_locked(self, locked):
        self.locked = bool(locked)
        self._write('locked', self.locked)
        self._apply_input_flags()
        self._sync_visibility()

    def set_click_through(self, enabled):
        self.click_through = bool(enabled)
        self._write('click_through', self.click_through)
        self._apply_input_flags()
        self._sync_visibility()

    def set_opacity(self, value):
        self.element_opacity = max(.2, min(1., _number(value, .95)))
        self._write('opacity', self.element_opacity)
        self.update()

    def set_preview(self, enabled):
        self._preview = bool(enabled)
        self._sync_visibility()

    def reset_position(self):
        self._offset = None
        self._write('position', None)
        self._sync_visibility()

    def _apply_input_flags(self):
        through = self.locked and self.click_through
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, through)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, through)
        self.setCursor(Qt.CursorShape.ArrowCursor if self.locked else Qt.CursorShape.SizeAllCursor)

    def _sync_visibility(self):
        if not self.enabled:
            self.hide()
            return
        if self._preview:
            self.show()
            return
        rectangle = self._game.rectangle(allow_app=not self.locked)
        if rectangle is None:
            self.hide()
            return
        self._game_rect = rectangle
        if self._drag is None:
            offset = QPoint(self._offset) if self._offset is not None else QPoint(10, round(rectangle.height() * .2))
            offset.setX(max(0, min(offset.x(), round(rectangle.width() - self.width()))))
            offset.setY(max(0, min(offset.y(), round(rectangle.height() - self.height()))))
            self.move(rectangle.topLeft().toPoint() + offset)
        self.show()

    def mousePressEvent(self, event):
        if not self.locked and event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.pos()
            event.accept()
        else: event.ignore()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            if self._game_rect is not None:
                self._offset = self.pos() - self._game_rect.topLeft().toPoint()
                self._write('position', [self._offset.x(), self._offset.y()])
            event.accept()

    def _text(self, painter, x, y, text, width=260, color='#f2f5f4', size=13):
        font = QFont('Malgun Gothic')
        font.setPixelSize(size)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        text = QFontMetricsF(font).elidedText(str(text), Qt.TextElideMode.ElideRight, width)
        painter.setPen(QColor(0, 0, 0, 175))
        painter.drawText(QPoint(x + 1, y + 1), text)
        painter.setPen(QColor(color))
        painter.drawText(QPoint(x, y), text)

    def _icon(self, painter, name, x, y, size):
        icon = item_icon(name)
        if not icon.isNull(): painter.drawPixmap(x, y, size, size, icon.pixmap(size * 2, size * 2))

    def _bar(self, painter, x, y, width, current, total, amber=False):
        current, total = _number(current), _number(total)
        fraction = min(1., current / total) if total else 0.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 85))
        painter.drawRoundedRect(QRectF(x, y, width, 4), 2, 2)
        painter.setBrush(QColor('#e7b76a' if amber else '#88cfae'))
        painter.drawRoundedRect(QRectF(x, y, width * fraction, 4), 2, 2)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(self.element_opacity)
        p.scale(SCALE, SCALE)
        data = self.payload
        name = str(data.get('recipe') or '제작 대기 중')
        stage = str(data.get('stage') or '작업 시작 대기')
        self._icon(p, name, 1, 5, 30)
        self._text(p, 40, 18, name, width=254, size=14)
        subtitle = (f"{_count(data.get('completed'))} / {_count(data.get('target'))}개" if _number(data.get('target'))
                    else '시설 생산 현황' if data.get('recipe') == '무한가공소' else '진행 수량 확인 중' if data else '작업을 시작해주세요')
        self._text(p, 40, 39, subtitle, width=114, size=12)
        self._text(p, 162, 39, stage, width=132, color='#c0ded0', size=12)
        if _number(data.get('target')): self._bar(p, 40, 48, 250, data.get('completed'), data.get('target'))
        materials = data.get('materials') or []
        if not isinstance(materials, (tuple, list)): materials = []
        limit = 4 if data.get('recipe') == '무한가공소' else 3
        for i, material in enumerate(materials[:limit]):
            if not isinstance(material, dict): continue
            y = 65 + i * (58 if limit == 4 else 70)
            name = str(material.get('name') or '')
            self._icon(p, name, 3, y, 25)
            owned, required = _number(material.get('owned')), _number(material.get('required'))
            ready = required > 0 and owned >= required
            state = str(material.get('state') or ('준비 완료' if ready else '재료 준비 중'))
            self._text(p, 40, y + 12, name, width=154)
            self._text(p, 197, y + 12, f'{_count(owned)} / {_count(required)}', width=96, size=12)
            self._text(p, 40, y + 32, state, width=174, color='#b8dfcb' if ready else '#efd2a0', size=12)
            if material.get('remaining_seconds') is not None:
                self._text(p, 215, y + 32, _time(material['remaining_seconds']), width=76, color='#efd2a0', size=12)
            self._bar(p, 40, y + 40, 250, owned, required, amber=not ready)
        message = str(data.get('message') or '')
        if len(materials) > limit: message = f'외 {len(materials) - limit}개 재료 · ' + message
        if message: self._text(p, 3, 312, message, width=290, color='#c6d3d0', size=11)
        p.end()
