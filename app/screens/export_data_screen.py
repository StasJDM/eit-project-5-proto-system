"""Окно ЭКСПОРТ ДАННЫХ.

Левая колонка:  Формат экспорта (JSON / EXCEL / CSV)
Правая колонка: История исследований
Нижняя строка:  Старт | Сбросить настройки | Сформировать
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt
from ..styles import C, configure_action_btn, yellow_btn_style, FONT_BASE, FONT_TITLE, FONT_SMALL
from ..i18n import t, i18n


# ── Style helpers ─────────────────────────────────────────────────────────────

def _fmt_btn_style() -> str:
    return yellow_btn_style() + f"""
        QPushButton[active="true"] {{
            background-color: #5a4500;
            border-color: {C['warn']};
            font-weight: bold;
        }}
    """

def _detail_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: #2a1400;
            color: {C['warn']};
            border: 1px solid #5a3000;
            border-radius: 3px;
            font-size: {FONT_SMALL}px;
            font-weight: 500;
            padding: 0 14px;
        }}
        QPushButton:hover {{ background-color: #3a1e00; }}
    """


# ── Section box ───────────────────────────────────────────────────────────────

class _SectionBox(QWidget):
    """Bordered card with a title header."""

    def __init__(self, title_key: str, parent=None):
        super().__init__(parent)
        self._title_key = title_key

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet(f"""
            background-color: {C['blue_dark']};
            border: 1px solid {C['border']};
            border-radius: 4px 4px 0 0;
        """)
        tbl = QHBoxLayout(title_bar)
        tbl.setContentsMargins(10, 0, 10, 0)
        self._lbl_title = QLabel(t(title_key))
        self._lbl_title.setStyleSheet(
            f"color: white; font-size: {FONT_TITLE}px; font-weight: bold; background: transparent;"
        )
        tbl.addWidget(self._lbl_title)
        root.addWidget(title_bar)

        self._body = QWidget()
        self._body.setStyleSheet(f"""
            background-color: {C['bg_panel']};
            border: 1px solid {C['border']};
            border-top: none;
            border-radius: 0 0 4px 4px;
        """)
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(10, 10, 10, 10)
        self._body_lay.setSpacing(8)
        root.addWidget(self._body)

    @property
    def body_layout(self):
        return self._body_lay

    def retranslate(self):
        self._lbl_title.setText(t(self._title_key))


# ── History row ───────────────────────────────────────────────────────────────

class _HistoryRow(QWidget):

    _ROW_H = 44
    _DATE_W = 108
    _BTN_W = 118
    _BTN_H = 34

    def __init__(self, date: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self._ROW_H)
        self.setStyleSheet(f"""
            background-color: {C['bg_card']};
            border: 1px solid {C['border']};
            border-radius: 3px;
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 8, 5)
        lay.setSpacing(12)

        self._lbl = QLabel(t("exp_prev_study"))
        self._lbl.setStyleSheet(
            f"color:{C['text']}; font-size:{FONT_BASE}px; background:transparent;"
        )
        lay.addWidget(self._lbl, stretch=1)

        lbl_date = QLabel(date)
        lbl_date.setFixedSize(self._DATE_W, self._BTN_H)
        lbl_date.setAlignment(Qt.AlignCenter)
        lbl_date.setStyleSheet(
            f"color:{C['text']}; font-size:{FONT_SMALL}px;"
            f"background:{C['bg_main']}; border:1px solid {C['border']};"
            f"border-radius:3px; padding:0 8px;"
        )
        lay.addWidget(lbl_date)

        btn = QPushButton(t("exp_btn_details"))
        btn.setFixedSize(self._BTN_W, self._BTN_H)
        btn.setStyleSheet(_detail_btn_style())
        self._btn = btn
        lay.addWidget(btn)

    def retranslate(self):
        self._lbl.setText(t("exp_prev_study"))
        self._btn.setText(t("exp_btn_details"))


# ── Export data screen ────────────────────────────────────────────────────────

class ExportDataScreen(QWidget):

    # Available export formats (label as shown on button)
    _FORMATS = ["JSON", "EXCEL", "CSV"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color:{C['bg_main']};")

        self._active_fmt = "JSON"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # ── Scroll wrapper ────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        outer.addWidget(scroll, stretch=1)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)

        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(10)

        # ── Two-column layout ─────────────────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(12)
        content_lay.addLayout(cols)

        # ── LEFT COLUMN — format selector ─────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(10)
        cols.addLayout(left, stretch=28)

        self._box_format = _SectionBox("exp_format_title")
        fmt_lay = self._box_format.body_layout
        fmt_lay.setSpacing(10)

        self._fmt_btns: dict[str, QPushButton] = {}
        for fmt in self._FORMATS:
            btn = QPushButton(fmt)
            btn.setFixedHeight(44)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(_fmt_btn_style())
            btn.clicked.connect(lambda checked=False, f=fmt: self._select_format(f))
            fmt_lay.addWidget(btn)
            self._fmt_btns[fmt] = btn

        fmt_lay.addStretch()
        left.addWidget(self._box_format)
        left.addStretch()

        self._select_format(self._active_fmt)

        # ── RIGHT COLUMN — study history ──────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(10)
        cols.addLayout(right, stretch=72)

        self._box_history = _SectionBox("exp_history_title")
        hist_lay = self._box_history.body_layout
        hist_lay.setSpacing(6)

        self._history_rows: list[_HistoryRow] = []
        for date in ["01.01.2025", "01.02.2025", "01.03.2025"]:
            row = _HistoryRow(date)
            self._history_rows.append(row)
            hist_lay.addWidget(row)

        hist_lay.addStretch()
        right.addWidget(self._box_history)
        right.addStretch()

        # ── Bottom action bar ─────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['border']};")
        outer.addWidget(sep)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        self._btn_start = QPushButton(t("btn_start"))
        self._btn_start.setObjectName("btn_start")
        self._btn_start.setFixedHeight(52)
        self._btn_start.setMinimumWidth(100)
        bottom.addWidget(self._btn_start)

        bottom.addStretch()

        self._btn_reset = QPushButton(t("exp_btn_reset"))
        configure_action_btn(self._btn_reset, 200)
        self._btn_reset.clicked.connect(self._reset_settings)
        bottom.addWidget(self._btn_reset)

        self._btn_generate = QPushButton(t("exp_btn_generate"))
        configure_action_btn(self._btn_generate, 160)
        bottom.addWidget(self._btn_generate)

        outer.addLayout(bottom)

        i18n.language_changed.connect(self.retranslate)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _select_format(self, fmt: str):
        self._active_fmt = fmt
        for f, btn in self._fmt_btns.items():
            btn.setProperty("active", "true" if f == fmt else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _reset_settings(self):
        self._select_format("JSON")

    # ── Retranslate ────────────────────────────────────────────────────────────

    def retranslate(self):
        self._box_format.retranslate()
        self._box_history.retranslate()
        for row in self._history_rows:
            row.retranslate()
        self._btn_start.setText(t("btn_start"))
        self._btn_reset.setText(t("exp_btn_reset"))
        self._btn_generate.setText(t("exp_btn_generate"))
