"""Системная информация — Table 7.5 of spec (12 parameters).

Row 11 (Date and time) updates every second via QTimer.
Row 12 (Interface language) has an inline «Change language» button.
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QDialog, QButtonGroup, QRadioButton,
)
from PySide6.QtCore import Qt, QTimer

from ..styles import C, FONT_BASE, FONT_SMALL, FONT_TITLE, FONT_LABEL, FONT_BTN
from ..i18n import t, i18n, LANGUAGES


# ── Language selector dialog ──────────────────────────────────────────────────

class LanguageDialog(QDialog):
    """Modal dialog for selecting the interface language."""

    _BTN_H = 40
    _BTN_MIN_W = 130

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("dlg_lang_title"))
        self.setFixedSize(360, 340)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {C['bg_panel']};
                color: {C['text']};
            }}
            QLabel {{
                background: transparent;
                color: {C['text']};
            }}
            QRadioButton {{
                background: transparent;
                color: {C['text']};
                font-size: {FONT_BASE}px;
                padding: 6px 12px;
                spacing: 10px;
                min-height: 28px;
            }}
            QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {C['border_light']};
                border-radius: 9px;
                background: {C['bg_main']};
            }}
            QRadioButton::indicator:checked {{
                background: {C['blue']};
                border-color: {C['blue_light']};
            }}
            QRadioButton:hover {{
                background-color: {C['nav_hover']};
                border-radius: 4px;
            }}
            QPushButton {{
                min-height: {self._BTN_H}px;
                padding: 8px 20px;
                font-size: {FONT_BASE}px;
                border-radius: 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        lbl_title = QLabel(t("dlg_lang_title"))
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet(f"font-size:18px;font-weight:bold;color:{C['text']};")
        layout.addWidget(lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['border']};")
        layout.addWidget(sep)

        self._group = QButtonGroup(self)
        self._radios: dict[str, QRadioButton] = {}

        for code in ("ru", "en", "zh", "vi"):
            rb = QRadioButton(LANGUAGES[code])
            rb.setChecked(code == i18n.lang)
            self._group.addButton(rb)
            self._radios[code] = rb
            layout.addWidget(rb)

        layout.addStretch()

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet(f"color:{C['border']};")
        layout.addWidget(sep2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_cancel = QPushButton(t("dlg_lang_cancel"))
        self.btn_cancel.setFixedHeight(self._BTN_H)
        self.btn_cancel.setMinimumWidth(self._BTN_MIN_W)
        self.btn_cancel.setAutoDefault(False)
        self.btn_cancel.setDefault(False)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['bg_nav']};
                color: {C['text']};
                border: 1px solid {C['border']};
            }}
            QPushButton:hover {{ background-color: {C['nav_hover']}; }}
        """)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_apply = QPushButton(t("dlg_lang_confirm"))
        self.btn_apply.setFixedHeight(self._BTN_H)
        self.btn_apply.setMinimumWidth(self._BTN_MIN_W)
        self.btn_apply.setAutoDefault(False)
        self.btn_apply.setDefault(True)
        self.btn_apply.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['ok']};
                color: white;
                border: 1px solid #1b5e20;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {C['ok_hover']}; }}
        """)
        self.btn_apply.clicked.connect(self._apply)

        btn_row.addStretch()
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_apply)
        layout.addLayout(btn_row)

    def _apply(self):
        for code, rb in self._radios.items():
            if rb.isChecked():
                i18n.set_language(code)
                break
        self.accept()


# ── Row definitions (Table 7.5) ───────────────────────────────────────────────
# (label_i18n_key, value_or_i18n_key, value_is_i18n, row_type)
# row_type: "static" | "translated" | "datetime" | "language"
_ROWS: list[tuple[str, str | None, bool, str]] = [
    ("sys_lbl_sw_name",      "sys_val_sw_name",   True,  "translated"),
    ("sys_lbl_version",      "1.1.1",             False, "static"),
    ("sys_lbl_release_date", "12.04.2026",        False, "static"),
    ("sys_lbl_serial",       "SN1234.12.12",      False, "static"),
    ("sys_lbl_device_model", "MD1234",            False, "static"),
    ("sys_lbl_electrodes",   "16",                False, "static"),
    ("sys_lbl_belts",        "1",                 False, "static"),
    ("sys_lbl_freq",         "sys_val_freq",      True,  "translated"),
    ("sys_lbl_current",      "sys_val_current",   True,  "translated"),
    ("sys_lbl_battery",      "60%",               False, "static"),
    ("sys_lbl_datetime",     None,                False, "datetime"),
    ("sys_lbl_language",     None,                False, "language"),
]

_ROW_H = 48
_NUM_W = 56


# ── System info screen ────────────────────────────────────────────────────────

class SystemInfoScreen(QWidget):
    """System information table — 12 parameters from spec Table 7.5."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color:{C['bg_main']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 30, 40, 30)
        outer.setSpacing(16)

        # Screen title
        self._lbl_title = QLabel(t("screen_system"))
        self._lbl_title.setAlignment(Qt.AlignCenter)
        self._lbl_title.setStyleSheet(
            f"color:{C['text']};font-size:26px;font-weight:bold;background:transparent;"
        )
        outer.addWidget(self._lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['border']};")
        outer.addWidget(sep)

        # Table container
        table = QWidget()
        table.setStyleSheet("background:transparent;")
        table_lay = QVBoxLayout(table)
        table_lay.setContentsMargins(0, 0, 0, 0)
        table_lay.setSpacing(0)
        outer.addWidget(table)

        # Header row
        self._lbl_h_num, self._lbl_h_param, self._lbl_h_value = \
            self._build_header(table_lay)

        # Data rows
        self._param_lbls: list[tuple[str, QLabel]] = []
        self._val_lbls: list[tuple[str, QLabel]] = []   # (i18n_key or "", label)
        self._datetime_lbl: QLabel | None = None
        self._lang_val_lbl: QLabel | None = None
        self._btn_change: QPushButton | None = None

        for i, row in enumerate(_ROWS):
            lbl_key, val_key, val_is_i18n, row_type = row
            self._build_row(table_lay, i + 1, lbl_key, val_key,
                            val_is_i18n, row_type, even=(i % 2 == 0))

        outer.addStretch()

        # Datetime ticker
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

        i18n.language_changed.connect(self.retranslate)

    # ── Row builders ──────────────────────────────────────────────────────────

    def _build_header(self, parent: QVBoxLayout) -> tuple[QLabel, QLabel, QLabel]:
        frame = QFrame()
        frame.setFixedHeight(_ROW_H)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {C['bg_nav']};
                border: 1px solid {C['border']};
                border-bottom: 2px solid {C['blue']};
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        h_num = self._hcell(t("sys_tbl_num"), _NUM_W, center=True)
        lay.addWidget(h_num)
        lay.addWidget(self._vsep())

        h_param = self._hcell(t("sys_tbl_param"))
        h_param.setContentsMargins(12, 4, 12, 4)
        lay.addWidget(h_param, stretch=2)
        lay.addWidget(self._vsep())

        h_value = self._hcell(t("sys_tbl_value"))
        h_value.setContentsMargins(12, 4, 12, 4)
        lay.addWidget(h_value, stretch=3)

        parent.addWidget(frame)
        return h_num, h_param, h_value

    def _build_row(
        self, parent: QVBoxLayout, num: int,
        lbl_key: str, val_key: str | None, val_is_i18n: bool,
        row_type: str, even: bool,
    ):
        bg = C['bg_card'] if even else C['bg_panel']
        frame = QFrame()
        frame.setFixedHeight(_ROW_H)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border-left: 1px solid {C['border']};
                border-right: 1px solid {C['border']};
                border-bottom: 1px solid {C['border']};
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # № column
        num_lbl = self._dcell(str(num), width=_NUM_W, dim=True, center=True)
        lay.addWidget(num_lbl)
        lay.addWidget(self._vsep())

        # Parameter name
        param_lbl = self._dcell(t(lbl_key))
        param_lbl.setContentsMargins(12, 4, 12, 4)
        self._param_lbls.append((lbl_key, param_lbl))
        lay.addWidget(param_lbl, stretch=2)
        lay.addWidget(self._vsep())

        # Value area
        val_widget = QWidget()
        val_widget.setStyleSheet("background:transparent;")
        val_lay = QHBoxLayout(val_widget)
        val_lay.setContentsMargins(12, 4, 12, 4)
        val_lay.setSpacing(8)

        if row_type == "datetime":
            lbl = self._dcell("", bold=True)
            self._datetime_lbl = lbl
            val_lay.addWidget(lbl)
            val_lay.addStretch()

        elif row_type == "language":
            lbl = self._dcell(LANGUAGES.get(i18n.lang, i18n.lang), bold=True)
            self._lang_val_lbl = lbl
            val_lay.addWidget(lbl)
            val_lay.addStretch()

            self._btn_change = QPushButton(t("sys_lang_change_btn"))
            self._btn_change.setFixedHeight(32)
            self._btn_change.setStyleSheet(f"""
                QPushButton {{
                    background-color: {C['blue']};
                    color: white;
                    border: 1px solid {C['blue_light']};
                    border-radius: 4px;
                    font-size: {FONT_BASE}px;
                    padding: 0 14px;
                }}
                QPushButton:hover {{ background-color: {C['blue_hover']}; }}
                QPushButton:pressed {{ background-color: {C['blue_dark']}; }}
            """)
            self._btn_change.clicked.connect(self._open_language_dialog)
            val_lay.addWidget(self._btn_change)

        else:
            value = t(val_key) if val_is_i18n else val_key
            i18n_key = val_key if val_is_i18n else ""
            lbl = self._dcell(value, bold=True)
            self._val_lbls.append((i18n_key, lbl))
            val_lay.addWidget(lbl)
            val_lay.addStretch()

        lay.addWidget(val_widget, stretch=3)
        parent.addWidget(frame)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _open_language_dialog(self):
        dlg = LanguageDialog(self)
        dlg.exec()

    def _tick(self):
        if self._datetime_lbl is not None:
            self._datetime_lbl.setText(
                datetime.now().strftime("%d.%m.%Y  %H:%M:%S")
            )

    def retranslate(self):
        self._lbl_title.setText(t("screen_system"))
        self._lbl_h_num.setText(t("sys_tbl_num"))
        self._lbl_h_param.setText(t("sys_tbl_param"))
        self._lbl_h_value.setText(t("sys_tbl_value"))

        for lbl_key, lbl in self._param_lbls:
            lbl.setText(t(lbl_key))

        for i18n_key, lbl in self._val_lbls:
            if i18n_key:
                lbl.setText(t(i18n_key))

        if self._lang_val_lbl is not None:
            self._lang_val_lbl.setText(LANGUAGES.get(i18n.lang, i18n.lang))

        if self._btn_change is not None:
            self._btn_change.setText(t("sys_lang_change_btn"))

    # ── Cell helpers ──────────────────────────────────────────────────────────

    def _hcell(self, text: str, width: int = -1, center: bool = False) -> QLabel:
        lbl = QLabel(text)
        if width > 0:
            lbl.setFixedWidth(width)
        lbl.setAlignment(Qt.AlignCenter if center else Qt.AlignVCenter | Qt.AlignLeft)
        lbl.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_BASE}px;font-weight:bold;background:transparent;"
        )
        return lbl

    def _dcell(self, text: str, width: int = -1, bold: bool = False,
               dim: bool = False, center: bool = False) -> QLabel:
        lbl = QLabel(text)
        if width > 0:
            lbl.setFixedWidth(width)
        lbl.setAlignment(Qt.AlignCenter if center else Qt.AlignVCenter | Qt.AlignLeft)
        color = C['text_dim'] if dim else C['text']
        weight = "bold" if bold else "normal"
        lbl.setStyleSheet(
            f"color:{color};font-size:{FONT_BASE}px;font-weight:{weight};background:transparent;"
        )
        return lbl

    def _vsep(self) -> QWidget:
        line = QWidget()
        line.setFixedWidth(1)
        line.setStyleSheet(f"background-color:{C['border']};")
        return line
