"""Right-side navigation panel.

Screen list matches п.6 ТЗ exactly (10 forms).
Supports runtime language switching via i18n.language_changed.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Qt, Signal
from ..i18n import t, i18n

from ..styles import C, FONT_NAV

_NAV_FONT = FONT_NAV
_NAV_PAD_V = 12
_NAV_PAD_H = 12
NAV_ITEMS = [
    ("main",         "nav_main"),
    ("patient",      "nav_patient"),
    ("trends",       "nav_trends"),
    ("analysis",     "nav_analysis"),
    ("eit_settings", "nav_eit_settings"),
    ("reports",      "nav_reports"),
    ("export",       "nav_export"),
    ("service",      "nav_service"),
    ("system",       "nav_system"),
    ("debug",        "nav_debug"),
]


class NavPanel(QWidget):
    """Vertical navigation panel with 10 buttons (one per TZ screen)."""

    screen_requested = Signal(str)   # emits screen key on click

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nav_panel")
        self.setFixedWidth(195)
        self.setStyleSheet(f"""
            QWidget#nav_panel {{
                background-color: {C['bg_nav']};
                border: none;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 5, 6)
        layout.setSpacing(0)

        self._buttons:  dict[str, QPushButton] = {}
        self._item_frames: dict[str, QWidget] = {}
        self._item_keys: list[tuple[str, str]]  = list(NAV_ITEMS)  # for retranslate

        for key, i18n_key in NAV_ITEMS:
            btn = self._make_btn(key, t(i18n_key))
            frame = QWidget(self)
            frame.setObjectName("nav_item_surround")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(4, 4, 4, 4)
            frame_layout.setSpacing(0)
            frame_layout.addWidget(btn)
            layout.addWidget(frame, stretch=1)
            self._buttons[key] = btn
            self._item_frames[key] = frame

        self._current = "main"
        self._set_active("main")

        i18n.language_changed.connect(self.retranslate)

    # ── Public ───────────────────────────────────────────────────────────────

    def set_active(self, key: str):
        self._set_active(key)

    def set_item_visible(self, key: str, visible: bool) -> None:
        if key in self._item_frames:
            self._item_frames[key].setVisible(visible)

    def is_item_visible(self, key: str) -> bool:
        return key in self._item_frames and not self._item_frames[key].isHidden()

    def retranslate(self):
        for key, i18n_key in self._item_keys:
            if key in self._buttons:
                self._buttons[key].setText(t(i18n_key))

    # ── Internals ─────────────────────────────────────────────────────────────

    def _make_btn(self, key: str, text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("nav_btn")
        btn.setMinimumHeight(44)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(self._btn_style(False))
        btn.clicked.connect(lambda _, k=key: self._on_click(k))
        return btn

    def _on_click(self, key: str):
        self._set_active(key)
        self.screen_requested.emit(key)

    def _set_active(self, key: str):
        if self._current != key and self._current in self._buttons:
            self._buttons[self._current].setStyleSheet(self._btn_style(False))
            self._set_surround_active(self._current, False)
        self._current = key
        if key in self._buttons:
            self._buttons[key].setStyleSheet(self._btn_style(True))
            self._set_surround_active(key, True)

    def _set_surround_active(self, key: str, active: bool) -> None:
        frame = self._item_frames[key]
        frame.setProperty("active", active)
        if active:
            frame.setStyleSheet(f"""
                QWidget#nav_item_surround {{
                    background-color: {C['nav_active_surround']};
                    border: 2px solid {C['nav_active_surround_edge']};
                    border-left: none;
                    border-top-left-radius: 0;
                    border-bottom-left-radius: 0;
                    border-top-right-radius: 10px;
                    border-bottom-right-radius: 10px;
                }}
            """)
        else:
            frame.setStyleSheet("""
                QWidget#nav_item_surround {
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: 10px;
                }
            """)

    def _btn_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background-color: {C['nav_active']};
                    color: white;
                    border: 1px solid {C['blue_light']};
                    border-radius: 6px;
                    text-align: left;
                    padding: {_NAV_PAD_V}px {_NAV_PAD_H}px;
                    font-size: {_NAV_FONT}px;
                    font-weight: bold;
                }}
            """
        return f"""
            QPushButton {{
                background-color: {C['bg_nav']};
                color: {C['text_dim']};
                border: 1px solid {C['border']};
                border-radius: 4px;
                text-align: left;
                padding: {_NAV_PAD_V}px {_NAV_PAD_H}px;
                font-size: {_NAV_FONT}px;
            }}
            QPushButton:hover {{
                background-color: {C['nav_hover']};
                color: {C['text']};
            }}
        """
