"""Base class for stub / placeholder screens.

Each subclass declares TITLE_KEY and SUBTITLE_KEY — i18n keys.
retranslate() is called automatically on language change.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QTimer
from ..styles import C, FONT_BASE
from ..i18n import t, i18n


class BaseScreen(QWidget):
    TITLE_KEY    = "screen_main"
    SUBTITLE_KEY = "sub_in_development"
    ICON         = "⬜"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color:{C['bg_main']};")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        lbl_icon = QLabel(self.ICON)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet("font-size:56px;background:transparent;color:#1e3a5f;")
        layout.addWidget(lbl_icon)

        self._lbl_title = QLabel(t(self.TITLE_KEY))
        self._lbl_title.setAlignment(Qt.AlignCenter)
        self._lbl_title.setStyleSheet(
            f"color:{C['text']};font-size:26px;font-weight:bold;background:transparent;"
        )
        layout.addWidget(self._lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedWidth(200)
        sep.setStyleSheet(f"color:{C['border']};")
        layout.addWidget(sep, alignment=Qt.AlignCenter)

        self._lbl_sub = QLabel(t(self.SUBTITLE_KEY))
        self._lbl_sub.setAlignment(Qt.AlignCenter)
        self._lbl_sub.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_BASE}px;background:transparent;"
        )
        layout.addWidget(self._lbl_sub)

        i18n.language_changed.connect(self.retranslate)

    def retranslate(self):
        self._lbl_title.setText(t(self.TITLE_KEY))
        self._lbl_sub.setText(t(self.SUBTITLE_KEY))


class LiveScreen(QWidget):
    """Refresh visible data immediately on navigation and on the display timer."""

    def start_refresh(self, interval_ms):
        self._paint_timer = QTimer(self)
        self._paint_timer.timeout.connect(self._refresh_tick)
        self._paint_timer.start(interval_ms)

    def _refresh_tick(self):
        if self.isVisible():
            self._on_paint()
        else:
            # Only the scale latch has a history-dependent first display.
            lung = self._scale_widget()
            if lung is not None:
                lung.observe_delta_scale(getattr(self._monitoring, "latest_delta_map", None))

    def _scale_widget(self):
        return None

    def showEvent(self, event):
        super().showEvent(event)
        self._on_paint()
