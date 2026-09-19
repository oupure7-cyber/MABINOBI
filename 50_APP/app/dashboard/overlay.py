"""In-game HUD overlays that float on top of the Mabinogi Mobile client window -
click-through, semi-transparent, continuously repositioned to track the game window as
the user freely moves/resizes it (user request, 2026-09-20).

Finds the game window purely via ctypes (stdlib, no new dependency) and never touches
the game process itself - no injection, no hooking. This project already learned the
hard way that touching the game process doesn't end well (README/CHANGELOG: embedding
the game window via reparenting was tried and abandoned because of the BlackCipher
안티치트) - every overlay here is just an ordinary top-level window that happens to sit
visually above the game window, exactly like a Discord/Steam "non-injected" overlay.

Panel sizes are FIXED (not adjustSize()-to-content) on purpose: an earlier version sized
itself to fit whatever text was already on screen and only then moved into place, so the
very first paint (still holding placeholder text like "-/7") was positioned using a
too-small size, landing the panel off from where the real, longer text would have
centered/anchored it. Fixed sizes make the position math depend only on the game
window's rect, never on the current label text.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QObject, QRect, Qt, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..cli_client import try_run_cli
from .altering_routine import FAMILIES

GAME_WINDOW_TITLE = "마비노기 모바일"
TRACK_INTERVAL_MS = 500  # position sync + data refresh cadence (user-specified)

# "시각적 투명도 80%" (80% see-through) was the original ask, but plain text at that
# opacity was reported unreadable against a busy game background - bumped up so the
# panel itself reads as a soft dark badge rather than near-invisible text floating in
# air. Still a see-through overlay, just no longer barely-there.
OVERLAY_BACKGROUND_OPACITY_PERCENT = 62

ACCENT = "#8bd8ae"       # app's mint accent (ui_kit.STYLE)
ACCENT_BRIGHT = "#5be08a"
DIM = "#4a6169"
TEXT = "#eaf2f0"

FACILITY_EMOJI = {"금속": "⚙️", "목재": "🪵", "가죽": "🟤", "옷감": "🧵"}
WEATHER_EMOJI = {
    "맑음": "☀️", "Sunny": "☀️", "Clear": "☀️",
    "흐림": "☁️", "Cloudy": "☁️",
    "비": "🌧️", "Rain": "🌧️", "Rainy": "🌧️",
    "눈": "❄️", "Snow": "❄️", "Snowy": "❄️",
    "안개": "🌫️", "Fog": "🌫️", "Foggy": "🌫️",
    "천둥": "⛈️", "번개": "⛈️", "Storm": "⛈️", "Thunder": "⛈️",
}

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetClientRect.restype = wintypes.BOOL
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.IsIconic.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]


def find_game_window_rect() -> QRect | None:
    """The game's client-area rect in screen coordinates, or None if the game isn't
    running / is minimized. Client rect (not the outer window rect) so the overlay
    aligns with the actual game content, not the title bar."""
    hwnd = user32.FindWindowW(None, GAME_WINDOW_TITLE)
    if not hwnd or user32.IsIconic(hwnd):
        return None
    client = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(client)):
        return None
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    return QRect(origin.x, origin.y, client.right - client.left, client.bottom - client.top)


def _weather_emoji(weather: str) -> str:
    return WEATHER_EMOJI.get(weather, "🌤️")


class OverlayWindow(QWidget):
    """Base for every overlay panel: frameless, always-on-top, click-through (mouse AND
    keyboard both pass through to whatever's underneath), fixed-size so position math
    never depends on the current content, background a soft rounded dark badge."""

    PANEL_SIZE: tuple[int, int] = (0, 0)

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if self.PANEL_SIZE != (0, 0):
            self.setFixedSize(*self.PANEL_SIZE)
        alpha = round(255 * OVERLAY_BACKGROUND_OPACITY_PERCENT / 100)
        self.setStyleSheet(f"""
            QWidget {{
                background: rgba(12, 22, 26, {alpha});
                border: 1px solid rgba(139, 216, 174, {min(alpha + 40, 255)});
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; color: {TEXT}; font-family: 'Malgun Gothic'; font-size: 12px; }}
        """)

    def reposition(self, game_rect: QRect) -> None:
        raise NotImplementedError

    def refresh_data(self) -> None:
        raise NotImplementedError


class FacilityOverlay(OverlayWindow):
    """좌중간: 4개 가공 시설(금속/목재/가죽/옷감) 대기열 상태, 최대한 작게."""

    PANEL_SIZE = (150, 118)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 7, 8, 7)
        v.setSpacing(3)
        self._rows: dict[str, tuple[str, QLabel]] = {}
        for family in FAMILIES:
            short = family.facility.replace(" 가공 시설", "")
            label = QLabel(f"{FACILITY_EMOJI.get(short, '🔧')} {short} ▱▱▱▱▱▱▱ -/7")
            v.addWidget(label)
            self._rows[family.facility] = (short, label)

    @staticmethod
    def _bar(occupied: int, done: int, total: int = 7) -> str:
        filled_done = f'<span style="color:{ACCENT_BRIGHT};">{"▰" * done}</span>'
        filled_pending = f'<span style="color:{ACCENT};">{"▰" * (occupied - done)}</span>'
        empty = f'<span style="color:{DIM};">{"▱" * (total - occupied)}</span>'
        return filled_done + filled_pending + empty

    def refresh_data(self) -> None:
        data = try_run_cli("get_altering_works", timeout=10)
        if not isinstance(data, dict):
            return  # keep showing the last known values rather than blanking out
        works = data.get("works", [])
        for facility, (short, label) in self._rows.items():
            occupied = sum(
                1 for w in works if w.get("FacilityName") == facility and w.get("State") in ("NotStarted", "InProgress", "Completed")
            )
            done = sum(1 for w in works if w.get("FacilityName") == facility and w.get("State") == "Completed")
            emoji = FACILITY_EMOJI.get(short, "🔧")
            bar = self._bar(occupied, done)
            html = f'{emoji} <b>{short}</b> {bar} <span style="color:#bdcbd0;">{occupied}/7</span>'
            if done:
                html += f' <span style="color:{ACCENT_BRIGHT};">{done}✓</span>'
            label.setText(html)

    def reposition(self, game_rect: QRect) -> None:
        x = game_rect.left() + 10
        y = game_rect.top() + game_rect.height() // 2 - self.height() // 2
        self.move(x, y)


class EnvironmentOverlay(OverlayWindow):
    """중상단: 인게임 날짜/시간/날씨/위치 (get_current_environment)."""

    PANEL_SIZE = (300, 44)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 4, 10, 4)
        self._label = QLabel("-")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        v.addWidget(self._label)

    def refresh_data(self) -> None:
        data = try_run_cli("get_current_environment", timeout=10)
        if not isinstance(data, dict):
            return
        place = data.get("GameSpaceDisplayName", "-")
        weather = data.get("Weather", "-")
        when = data.get("ErinnNow", "-")
        html = (
            f'<b>📍 {place}</b>'
            f' <span style="color:{DIM};">|</span> {_weather_emoji(weather)} {weather}'
            f' <span style="color:{DIM};">|</span> 🕐 {when}'
        )
        self._label.setText(html)

    def reposition(self, game_rect: QRect) -> None:
        x = game_rect.left() + game_rect.width() // 2 - self.width() // 2
        y = game_rect.top() + 16
        self.move(x, y)


class OverlayManager(QObject):
    """Owns every overlay panel and the single timer that both re-tracks the game
    window's position and refreshes each panel's data, every TRACK_INTERVAL_MS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.panels: list[OverlayWindow] = [FacilityOverlay(parent), EnvironmentOverlay(parent)]
        self._enabled = False
        self._timer = QTimer(self)
        self._timer.setInterval(TRACK_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        if enabled:
            self._timer.start()
            self._tick()
        else:
            self._timer.stop()
            for panel in self.panels:
                panel.hide()

    def _tick(self) -> None:
        game_rect = find_game_window_rect()
        if game_rect is None:
            for panel in self.panels:
                panel.hide()
            return
        for panel in self.panels:
            panel.refresh_data()   # update content first - size is fixed, but keep data
            panel.reposition(game_rect)  # fresh before the panel is (re)placed and shown
            panel.show()
