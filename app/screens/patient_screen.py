"""Окно ПАЦИЕНТ.

Левая колонка:  Карточка пациента
Правая колонка: Клинические данные + История исследований
Нижняя строка:  Старт | Сохранить карточку | Привязать исследование
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QScrollArea, QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt
from ..styles import (
    C, FONT_BASE, FONT_TITLE, FONT_SMALL,
    FONT_BTN, FONT_BTN_START,
    configure_action_btn, yellow_btn_style,
)
from ..i18n import t, i18n


# ── Style helpers ─────────────────────────────────────────────────────────────

_FIELD_MIN_H = 28
_DETAIL_BTN_H = 32
_DETAIL_BTN_W = 110


def _field_style() -> str:
    return f"""
        QLineEdit {{
            background-color: {C['bg_card']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 3px;
            padding: 3px 8px;
            font-size: {FONT_BASE}px;
            min-height: {_FIELD_MIN_H}px;
        }}
        QLineEdit:focus {{
            border-color: {C['blue_light']};
        }}
        QLineEdit:read-only {{
            color: {C['text_dim']};
        }}
    """

def _combo_style() -> str:
    return f"""
        QComboBox {{
            background-color: {C['bg_card']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 3px;
            padding: 4px 8px;
            font-size: {FONT_BASE}px;
            min-height: {_FIELD_MIN_H}px;
        }}
        QComboBox:focus {{ border-color: {C['blue_light']}; }}
        QComboBox QAbstractItemView {{
            background-color: {C['bg_panel']};
            color: {C['text']};
            selection-background-color: {C['blue']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
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
            padding: 4px 10px;
        }}
        QPushButton:hover {{ background-color: #3a1e00; }}
    """

def _start_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: {C['ok']};
            color: white;
            font-size: {FONT_BTN_START}px;
            font-weight: bold;
            padding: 8px 20px;
            border: 1px solid #1b5e20;
            border-radius: 4px;
        }}
        QPushButton:hover {{ background-color: {C['ok_hover']}; }}
        QPushButton:pressed {{ background-color: #1b5e20; }}
    """

def _label_style(dim: bool = False) -> str:
    color = C['text_dim'] if dim else C['text']
    return f"color: {color}; font-size: {FONT_SMALL}px; background: transparent;"


# ── Section box ───────────────────────────────────────────────────────────────

class _SectionBox(QWidget):
    """Bordered card with a title header."""

    def __init__(self, title_key: str, parent=None):
        super().__init__(parent)
        self._title_key = title_key
        self.setStyleSheet(f"""
            _SectionBox, QWidget#section_box {{
                background-color: {C['bg_panel']};
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
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

        # Body
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


# ── Field row helper ──────────────────────────────────────────────────────────

class _FieldRow(QWidget):
    """Label on top, input widget below (for compact grid cells)."""

    def __init__(self, label_key: str, widget: QWidget, parent=None):
        super().__init__(parent)
        self._label_key = label_key
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self._lbl = QLabel(t(label_key))
        self._lbl.setStyleSheet(_label_style(dim=True))
        self._lbl.setWordWrap(True)
        self._lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lay.addWidget(self._lbl)
        lay.addWidget(widget)

    def retranslate(self):
        self._lbl.setText(t(self._label_key))


# ── History row ───────────────────────────────────────────────────────────────

class _HistoryRow(QWidget):
    """Single row in the study history list."""

    def __init__(self, date: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet(f"""
            background-color: {C['bg_card']};
            border: 1px solid {C['border']};
            border-radius: 3px;
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 8, 4)
        lay.setSpacing(10)

        self._lbl = QLabel(t("pat_prev_study"))
        self._lbl.setStyleSheet(f"color:{C['text']}; font-size:{FONT_BASE}px; background:transparent;")
        lay.addWidget(self._lbl, stretch=1)

        lbl_date = QLabel(date)
        lbl_date.setFixedWidth(80)
        lbl_date.setAlignment(Qt.AlignCenter)
        lbl_date.setStyleSheet(f"color:{C['text_dim']}; font-size:{FONT_SMALL}px; background:transparent;")
        lay.addWidget(lbl_date)

        btn = QPushButton(t("pat_details"))
        btn.setFixedSize(_DETAIL_BTN_W, _DETAIL_BTN_H)
        btn.setStyleSheet(_detail_btn_style())
        lay.addWidget(btn)

    def retranslate(self):
        # label inside lay, index 0
        self._lbl.setText(t("pat_prev_study"))


# ── Patient screen ────────────────────────────────────────────────────────────

class PatientScreen(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color:{C['bg_main']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # ── Scroll area for content ───────────────────────────────────────────
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

        # ── LEFT COLUMN ───────────────────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(10)
        cols.addLayout(left, stretch=42)

        # · Карточка пациента ·················································
        self._box_card = _SectionBox("pat_card_title")
        card_lay = self._box_card.body_layout

        # Row 1: Фамилия | Имя | Отчество
        r1 = QHBoxLayout(); r1.setSpacing(8)
        self._e_last  = QLineEdit(); self._e_last.setStyleSheet(_field_style())
        self._e_first = QLineEdit(); self._e_first.setStyleSheet(_field_style())
        self._e_patr  = QLineEdit(); self._e_patr.setStyleSheet(_field_style())
        self._fr_last  = _FieldRow("pat_last_name",   self._e_last)
        self._fr_first = _FieldRow("pat_first_name",  self._e_first)
        self._fr_patr  = _FieldRow("pat_patronymic",  self._e_patr)
        r1.addWidget(self._fr_last);  r1.addWidget(self._fr_first);  r1.addWidget(self._fr_patr)
        card_lay.addLayout(r1)

        # Row 2: Дата рождения | Пол | Номер истории болезни
        r2 = QHBoxLayout(); r2.setSpacing(8)
        self._e_dob    = QLineEdit(); self._e_dob.setPlaceholderText("дд.мм.гггг")
        self._e_dob.setStyleSheet(_field_style())
        self._cmb_gender = QComboBox()
        self._cmb_gender.setStyleSheet(_combo_style())
        self._cmb_gender.addItems([t("pat_gender_m"), t("pat_gender_f")])
        self._e_record = QLineEdit(); self._e_record.setStyleSheet(_field_style())
        self._fr_dob    = _FieldRow("pat_dob",        self._e_dob)
        self._fr_gender = _FieldRow("pat_gender",     self._cmb_gender)
        self._fr_record = _FieldRow("pat_record_num", self._e_record)
        r2.addWidget(self._fr_dob, stretch=2)
        r2.addWidget(self._fr_gender, stretch=1)
        r2.addWidget(self._fr_record, stretch=2)
        card_lay.addLayout(r2)

        # Row 3: Вес | Рост | ID
        r3 = QHBoxLayout(); r3.setSpacing(8)
        self._e_weight = QLineEdit(); self._e_weight.setStyleSheet(_field_style())
        self._e_height = QLineEdit(); self._e_height.setStyleSheet(_field_style())
        self._e_id     = QLineEdit(); self._e_id.setStyleSheet(_field_style())
        self._fr_weight = _FieldRow("pat_weight", self._e_weight)
        self._fr_height = _FieldRow("pat_height", self._e_height)
        self._fr_id     = _FieldRow("pat_id",     self._e_id)
        r3.addWidget(self._fr_weight); r3.addWidget(self._fr_height); r3.addWidget(self._fr_id)
        card_lay.addLayout(r3)

        # Row 4: Охват грудной клетки | Полных лет | Присвоить код ID
        r4 = QHBoxLayout(); r4.setSpacing(8)
        self._e_chest = QLineEdit(); self._e_chest.setStyleSheet(_field_style())
        self._e_age   = QLineEdit(); self._e_age.setReadOnly(True)
        self._e_age.setStyleSheet(_field_style())
        self._btn_assign_id = QPushButton(t("pat_assign_id"))
        self._btn_assign_id.setFixedHeight(_FIELD_MIN_H + 4)
        self._btn_assign_id.setStyleSheet(yellow_btn_style())
        self._fr_chest = _FieldRow("pat_chest", self._e_chest)
        self._fr_age   = _FieldRow("pat_age",   self._e_age)
        r4.addWidget(self._fr_chest, stretch=2)
        r4.addWidget(self._fr_age,   stretch=1)
        assign_wrap = QWidget(); assign_wrap.setStyleSheet("background:transparent;")
        aw_lay = QVBoxLayout(assign_wrap); aw_lay.setContentsMargins(0, 0, 0, 0); aw_lay.setSpacing(3)
        aw_lay.addWidget(QLabel(" ", styleSheet="background:transparent; font-size:1px;"))
        aw_lay.addWidget(self._btn_assign_id)
        r4.addWidget(assign_wrap, stretch=2)
        card_lay.addLayout(r4)

        left.addWidget(self._box_card)
        left.addStretch()

        # ── RIGHT COLUMN ──────────────────────────────────────────────────────
        right = QVBoxLayout()
        right.setSpacing(10)
        cols.addLayout(right, stretch=58)

        # · Клинические данные ·················································
        self._box_clinical = _SectionBox("pat_clinical_title")
        clin_lay = self._box_clinical.body_layout

        # Main diagnosis
        self._lbl_main_diag = QLabel(t("pat_main_diag"))
        self._lbl_main_diag.setStyleSheet(_label_style(dim=True))
        self._lbl_main_diag.setWordWrap(True)
        clin_lay.addWidget(self._lbl_main_diag)
        d1_row = QHBoxLayout(); d1_row.setSpacing(8)
        self._e_main_diag = QLineEdit(); self._e_main_diag.setPlaceholderText(t("pat_icd_code"))
        self._e_main_diag.setStyleSheet(_field_style())
        self._btn_detail1 = QPushButton(t("pat_details"))
        self._btn_detail1.setFixedSize(_DETAIL_BTN_W, _DETAIL_BTN_H)
        self._btn_detail1.setStyleSheet(_detail_btn_style())
        d1_row.addWidget(self._e_main_diag, stretch=1)
        d1_row.addWidget(self._btn_detail1)
        clin_lay.addLayout(d1_row)

        # Accompanying diagnosis
        self._lbl_acc_diag = QLabel(t("pat_accompany_diag"))
        self._lbl_acc_diag.setStyleSheet(_label_style(dim=True))
        self._lbl_acc_diag.setWordWrap(True)
        clin_lay.addWidget(self._lbl_acc_diag)
        d2_row = QHBoxLayout(); d2_row.setSpacing(8)
        self._e_acc_diag = QLineEdit(); self._e_acc_diag.setPlaceholderText(t("pat_icd_code"))
        self._e_acc_diag.setStyleSheet(_field_style())
        self._btn_detail2 = QPushButton(t("pat_details"))
        self._btn_detail2.setFixedSize(_DETAIL_BTN_W, _DETAIL_BTN_H)
        self._btn_detail2.setStyleSheet(_detail_btn_style())
        d2_row.addWidget(self._e_acc_diag, stretch=1)
        d2_row.addWidget(self._btn_detail2)
        clin_lay.addLayout(d2_row)

        # ИВЛ
        ivl_row = QHBoxLayout(); ivl_row.setSpacing(10)
        self._lbl_ivl = QLabel(t("pat_ivl"))
        self._lbl_ivl.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_SMALL}px;font-weight:500;background:transparent;"
        )
        self._btn_ivl_yes = QPushButton(t("pat_yes"))
        self._btn_ivl_no  = QPushButton(t("pat_no"))
        self._btn_ivl_yes.setFixedSize(64, _DETAIL_BTN_H)
        self._btn_ivl_no.setFixedSize(64, _DETAIL_BTN_H)
        self._btn_detail3 = QPushButton(t("pat_details"))
        self._btn_detail3.setFixedSize(_DETAIL_BTN_W, _DETAIL_BTN_H)
        self._btn_detail3.setStyleSheet(_detail_btn_style())
        self._ivl_state = "no"
        self._btn_ivl_yes.clicked.connect(lambda: self._set_ivl("yes"))
        self._btn_ivl_no.clicked.connect(lambda: self._set_ivl("no"))
        self._set_ivl("no")
        ivl_row.addWidget(self._lbl_ivl)
        ivl_row.addWidget(self._btn_ivl_yes)
        ivl_row.addWidget(self._btn_ivl_no)
        ivl_row.addStretch()
        ivl_row.addWidget(self._btn_detail3)
        clin_lay.addLayout(ivl_row)

        right.addWidget(self._box_clinical)

        # · История исследований ···············································
        self._box_history = _SectionBox("pat_history_title")
        hist_lay = self._box_history.body_layout
        hist_lay.setSpacing(6)

        self._history_rows: list[_HistoryRow] = []
        for date in ["01.01.2025", "01.02.2025", "01.03.2025"]:
            row = _HistoryRow(date)
            self._history_rows.append(row)
            hist_lay.addWidget(row)

        right.addWidget(self._box_history)
        right.addStretch()

        # ── Bottom action bar ─────────────────────────────────────────────────
        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.HLine)
        self._sep.setStyleSheet(f"color:{C['border']};")
        outer.addWidget(self._sep)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        self._btn_start = QPushButton("▶  " + t("btn_start").replace("▶  ", ""))
        self._btn_start.setFixedHeight(52)
        self._btn_start.setStyleSheet(_start_btn_style())
        bottom.addWidget(self._btn_start)

        bottom.addStretch()

        self._btn_save = QPushButton(t("pat_save_card"))
        configure_action_btn(self._btn_save, 200)
        bottom.addWidget(self._btn_save)

        self._btn_link = QPushButton(t("pat_link_study"))
        configure_action_btn(self._btn_link, 340)
        bottom.addWidget(self._btn_link)

        outer.addLayout(bottom)

        i18n.language_changed.connect(self.retranslate)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _set_ivl(self, state: str):
        self._ivl_state = state
        active = f"""
            QPushButton {{
                background-color: {C['blue']};
                color: white;
                border: 1px solid {C['blue_light']};
                border-radius: 3px;
                font-size: {FONT_BTN}px; font-weight: bold;
            }}
        """
        inactive = f"""
            QPushButton {{
                background-color: {C['bg_card']};
                color: {C['text_dim']};
                border: 1px solid {C['border']};
                border-radius: 3px;
                font-size: {FONT_BTN}px;
            }}
            QPushButton:hover {{ background-color: {C['nav_hover']}; }}
        """
        self._btn_ivl_yes.setStyleSheet(active if state == "yes" else inactive)
        self._btn_ivl_no.setStyleSheet(active if state == "no"  else inactive)

    # ── Retranslate ────────────────────────────────────────────────────────────

    def retranslate(self):
        for box in (self._box_card, self._box_clinical, self._box_history):
            box.retranslate()
        for fr in (self._fr_last, self._fr_first, self._fr_patr,
                   self._fr_dob, self._fr_gender, self._fr_record,
                   self._fr_weight, self._fr_height, self._fr_id,
                   self._fr_chest, self._fr_age):
            fr.retranslate()

        # Combo items
        self._cmb_gender.setItemText(0, t("pat_gender_m"))
        self._cmb_gender.setItemText(1, t("pat_gender_f"))

        self._btn_assign_id.setText(t("pat_assign_id"))

        self._lbl_main_diag.setText(t("pat_main_diag"))
        self._lbl_acc_diag.setText(t("pat_accompany_diag"))
        self._e_main_diag.setPlaceholderText(t("pat_icd_code"))
        self._e_acc_diag.setPlaceholderText(t("pat_icd_code"))
        self._lbl_ivl.setText(t("pat_ivl"))
        self._btn_ivl_yes.setText(t("pat_yes"))
        self._btn_ivl_no.setText(t("pat_no"))
        for b in (self._btn_detail1, self._btn_detail2, self._btn_detail3):
            b.setText(t("pat_details"))

        for row in self._history_rows:
            row.retranslate()

        self._btn_save.setText(t("pat_save_card"))
        self._btn_link.setText(t("pat_link_study"))
