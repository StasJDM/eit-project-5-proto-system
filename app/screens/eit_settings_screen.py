"""Окно НАСТРОЙКИ ЭИТ.

Левая колонка:  Сила тока, Частота, Количество электродов, Количество поясов
Правая колонка: Цвет визуализации (2 цвета / Стандартное), Тип дыхания (Да / Нет)
Нижняя строка:  Старт | Сбросить настройки | Сохранить настройки ЭИТ-исследования
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt
from ..styles import C, configure_action_btn, FONT_BASE, FONT_LABEL, FONT_BTN, FONT_SMALL
from ..i18n import t, i18n


# ── Style helpers ─────────────────────────────────────────────────────────────

def _field_style() -> str:
    return f"""
        QLineEdit {{
            background-color: {C['bg_card']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 3px;
            padding: 4px 8px;
            font-size: {FONT_BASE}px;
            min-height: 36px;
        }}
        QLineEdit:focus {{ border-color: {C['blue_light']}; }}
    """

def _toggle_active_style() -> str:
    return f"""
        QPushButton {{
            background-color: {C['blue']};
            color: white;
            border: 1px solid {C['blue_light']};
            border-radius: 4px;
            font-size: {FONT_BTN}px;
            font-weight: bold;
            padding: 8px 16px;
            min-height: 36px;
        }}
        QPushButton:hover {{ background-color: {C['blue_hover']}; }}
    """

def _toggle_inactive_style() -> str:
    return f"""
        QPushButton {{
            background-color: {C['bg_card']};
            color: {C['text_dim']};
            border: 1px solid {C['border']};
            border-radius: 4px;
            font-size: {FONT_BTN}px;
            padding: 8px 16px;
            min-height: 36px;
        }}
        QPushButton:hover {{ background-color: {C['nav_hover']}; }}
    """

def _label_style() -> str:
    return f"color:{C['text_dim']}; font-size:{FONT_LABEL}px; background:transparent;"

def _sublabel_style() -> str:
    return (
        f"color:{C['text']}; font-size:{FONT_LABEL}px; font-weight:500; "
        "background:transparent; text-align:center;"
    )


# ── Параметр с полем ввода и единицей измерения ───────────────────────────────

class _ParamRow(QWidget):
    """Label / [input field] [unit]."""

    def __init__(self, label_key: str, placeholder_key: str, unit_key: str,
                 default: str = "", parent=None):
        super().__init__(parent)
        self._label_key = label_key
        self._placeholder_key = placeholder_key
        self._unit_key = unit_key
        self.setStyleSheet("background:transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self._lbl = QLabel(t(label_key))
        self._lbl.setStyleSheet(_label_style())
        lay.addWidget(self._lbl)

        row = QHBoxLayout()
        row.setSpacing(6)

        self._edit = QLineEdit(default)
        self._edit.setPlaceholderText(t(placeholder_key))
        self._edit.setStyleSheet(_field_style())
        row.addWidget(self._edit, stretch=1)

        self._lbl_unit = QLabel(t(unit_key))
        self._lbl_unit.setFixedWidth(36)
        self._lbl_unit.setStyleSheet(
            f"color:{C['text_dim']}; font-size:{FONT_LABEL}px; background:transparent;"
        )
        row.addWidget(self._lbl_unit)

        lay.addLayout(row)

    def retranslate(self):
        self._lbl.setText(t(self._label_key))
        self._edit.setPlaceholderText(t(self._placeholder_key))
        self._lbl_unit.setText(t(self._unit_key))


# ── Группа переключателей (два варианта) ──────────────────────────────────────

class _ToggleGroup(QWidget):
    """Label + two mutually-exclusive toggle buttons."""

    def __init__(self, label_key: str, opt_a_key: str, opt_b_key: str,
                 default: str = "a", parent=None):
        super().__init__(parent)
        self._label_key = label_key
        self._opt_a_key = opt_a_key
        self._opt_b_key = opt_b_key
        self._state = default
        self.setStyleSheet("background:transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._lbl = QLabel(t(label_key))
        self._lbl.setAlignment(Qt.AlignCenter)
        self._lbl.setWordWrap(True)
        self._lbl.setStyleSheet(_sublabel_style())
        lay.addWidget(self._lbl)

        btns = QHBoxLayout()
        btns.setSpacing(12)

        self._btn_a = QPushButton(t(opt_a_key))
        self._btn_a.setMinimumWidth(120)
        self._btn_a.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_a.clicked.connect(lambda: self._select("a"))

        self._btn_b = QPushButton(t(opt_b_key))
        self._btn_b.setMinimumWidth(120)
        self._btn_b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_b.clicked.connect(lambda: self._select("b"))

        btns.addWidget(self._btn_a)
        btns.addWidget(self._btn_b)
        lay.addLayout(btns)

        self._select(default)

    def _select(self, state: str):
        self._state = state
        self._btn_a.setStyleSheet(
            _toggle_active_style() if state == "a" else _toggle_inactive_style()
        )
        self._btn_b.setStyleSheet(
            _toggle_active_style() if state == "b" else _toggle_inactive_style()
        )

    def retranslate(self):
        self._lbl.setText(t(self._label_key))
        self._btn_a.setText(t(self._opt_a_key))
        self._btn_b.setText(t(self._opt_b_key))
        self._select(self._state)


# ── EIT settings screen ───────────────────────────────────────────────────────

class EITSettingsScreen(QWidget):

    # Default hardware values
    _DEFAULT_CURRENT    = "0,5–5"
    _DEFAULT_FREQ       = "10–500"
    _DEFAULT_ELECTRODES = "16"
    _DEFAULT_BELTS      = "1"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color:{C['bg_main']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(14)

        # ── Main content row ──────────────────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(40)
        outer.addLayout(cols, stretch=1)

        # ── LEFT COLUMN — hardware parameters ─────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(20)
        cols.addLayout(left, stretch=45)

        self._row_current = _ParamRow(
            "eit_current_label", "eit_current_placeholder", "eit_unit_ma",
            default=self._DEFAULT_CURRENT,
        )
        self._row_freq = _ParamRow(
            "eit_freq_label", "eit_freq_placeholder", "eit_unit_khz",
            default=self._DEFAULT_FREQ,
        )
        self._row_electrodes = _ParamRow(
            "eit_electrodes_label", "eit_electrodes_label", "eit_unit_pcs",
            default=self._DEFAULT_ELECTRODES,
        )
        self._row_belts = _ParamRow(
            "eit_belts_label", "eit_belts_label", "eit_unit_pcs",
            default=self._DEFAULT_BELTS,
        )

        for row in (self._row_current, self._row_freq,
                    self._row_electrodes, self._row_belts):
            left.addWidget(row)

        left.addStretch()

        # ── RIGHT COLUMN — display settings ───────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(36)
        cols.addLayout(right, stretch=55)

        right.addStretch()

        self._grp_color = _ToggleGroup(
            "eit_viz_color_label", "eit_viz_2colors", "eit_viz_standard",
            default="a",
        )
        right.addWidget(self._grp_color)

        right.addStretch()

        self._grp_pathology = _ToggleGroup(
            "eit_pathology_label", "pat_yes", "pat_no",
            default="a",
        )
        right.addWidget(self._grp_pathology)

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

        self._btn_reset = QPushButton(t("eit_btn_reset"))
        configure_action_btn(self._btn_reset, 180)
        self._btn_reset.clicked.connect(self._reset)
        bottom.addWidget(self._btn_reset)

        self._btn_save = QPushButton(t("eit_btn_save"))
        configure_action_btn(self._btn_save, 280)
        bottom.addWidget(self._btn_save)

        outer.addLayout(bottom)

        i18n.language_changed.connect(self.retranslate)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _reset(self):
        self._row_current._edit.setText(self._DEFAULT_CURRENT)
        self._row_freq._edit.setText(self._DEFAULT_FREQ)
        self._row_electrodes._edit.setText(self._DEFAULT_ELECTRODES)
        self._row_belts._edit.setText(self._DEFAULT_BELTS)
        self._grp_color._select("a")
        self._grp_pathology._select("a")

    # ── Retranslate ────────────────────────────────────────────────────────────

    def retranslate(self):
        for row in (self._row_current, self._row_freq,
                    self._row_electrodes, self._row_belts):
            row.retranslate()
        self._grp_color.retranslate()
        self._grp_pathology.retranslate()
        self._btn_start.setText(t("btn_start"))
        self._btn_reset.setText(t("eit_btn_reset"))
        self._btn_save.setText(t("eit_btn_save"))
