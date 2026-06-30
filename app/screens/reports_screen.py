"""Окно ОТЧЁТЫ.

Алгоритм взаимодействия (рис. 7.11):
  1. Загрузка и отображение списка сохранённых отчётов (дата, наименование, пациент)
  2. Действие пользователя:
     а) «Сформировать отчёт» → выбор параметров → формирование → сохранение
     б) «Просмотр / Печать»  → открытие выбранного отчёта
     в) «Навигация»          → переход в выбранное окно

Макет:
  ┌─ Левая колонка (38%) ────────┬─ Правая колонка (62%) ──────────────────┐
  │  Сохранённые отчёты           │  Сформировать новый отчёт               │
  │  [+ Новый отчёт]              │  Период / Пациент / Наименование        │
  │  [строка 1] [Просмотр][Печать]│  [Сформировать]                         │
  │  [строка 2] ...               │  ── Предварительный просмотр ────────── │
  │  ...                          │  (текст отчёта или заглушка)            │
  └──────────────────────────────┴─────────────────────────────────────────┘
  [Старт] ─────────────────────────────────── [Сбросить] [Печать]
"""

import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QScrollArea, QSizePolicy,
    QTextEdit, QStackedWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ..styles import C, configure_action_btn, yellow_btn_style, FONT_BASE, FONT_SMALL, FONT_TITLE
from ..i18n import t, i18n


# ── Мок-данные ────────────────────────────────────────────────────────────────

_MOCK_PATIENTS = [
    "Иванов Иван Иванович",
    "Петрова Анна Сергеевна",
    "Сидоров Виктор Николаевич",
    "Козлова Мария Юрьевна",
    "Новиков Павел Дмитриевич",
]

_MOCK_REPORTS = [
    ("Исследование ЭИТ №001", _MOCK_PATIENTS[0], "12.01.2025 09:15", 1),
    ("Исследование ЭИТ №002", _MOCK_PATIENTS[1], "18.01.2025 14:30", 2),
    ("Исследование ЭИТ №003", _MOCK_PATIENTS[2], "25.01.2025 11:00", 3),
    ("Исследование ЭИТ №004", _MOCK_PATIENTS[3], "02.02.2025 16:45", 4),
    ("Исследование ЭИТ №005", _MOCK_PATIENTS[4], "10.02.2025 08:20", 5),
]


# ── Стили ─────────────────────────────────────────────────────────────────────

def _field_style() -> str:
    return f"""
        QLineEdit {{
            background:{C['bg_card']}; color:{C['text']};
            border:1px solid {C['border']}; border-radius:3px;
            padding:4px 8px; font-size:{FONT_BASE}px; min-height:36px;
        }}
        QLineEdit:focus {{ border-color:{C['blue_light']}; }}
    """

def _combo_style() -> str:
    return f"""
        QComboBox {{
            background:{C['bg_card']}; color:{C['text']};
            border:1px solid {C['border']}; border-radius:3px;
            padding:4px 8px; font-size:{FONT_BASE}px; min-height:36px;
        }}
        QComboBox:focus {{ border-color:{C['blue_light']}; }}
        QComboBox QAbstractItemView {{
            background:{C['bg_panel']}; color:{C['text']};
            selection-background-color:{C['blue']};
        }}
        QComboBox::drop-down {{ border:none; width:20px; }}
    """

def _row_action_btn_style() -> str:
    return f"""
        QPushButton {{
            background-color: #2a1400;
            color: {C['warn']};
            border: 1px solid #5a3000;
            border-radius: 4px;
            font-size: {FONT_BASE}px;
            font-weight: 500;
            padding: 0 16px;
        }}
        QPushButton:hover {{ background-color: #3a1e00; }}
    """

def _hsep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{C['border']};margin:2px 0;")
    return f


# ── Секция с заголовком ───────────────────────────────────────────────────────

class _SectionBox(QWidget):
    def __init__(self, title_key: str, parent=None):
        super().__init__(parent)
        self._title_key = title_key
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QWidget()
        hdr.setFixedHeight(28)
        hdr.setStyleSheet(
            f"background:{C['blue_dark']};border:1px solid {C['border']};"
            "border-radius:4px 4px 0 0;"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(10, 0, 10, 0)
        self._lbl = QLabel(t(title_key))
        self._lbl.setStyleSheet(
            f"color:white;font-size:{FONT_TITLE}px;font-weight:bold;background:transparent;"
        )
        hl.addWidget(self._lbl)
        root.addWidget(hdr)

        self._body = QWidget()
        self._body.setStyleSheet(
            f"background:{C['bg_panel']};border:1px solid {C['border']};"
            "border-top:none;border-radius:0 0 4px 4px;"
        )
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(10, 10, 10, 10)
        self._body_lay.setSpacing(8)
        root.addWidget(self._body)

    @property
    def body_layout(self):
        return self._body_lay

    def retranslate(self):
        self._lbl.setText(t(self._title_key))


# ── Строка отчёта ─────────────────────────────────────────────────────────────

class _ReportRow(QWidget):

    _ROW_H = 80
    _BTN_H = 40
    _BTN_W_VIEW = 132
    _BTN_W_PRINT = 120

    def __init__(self, name: str, patient: str, date: str,
                 on_view, on_print, parent=None):
        super().__init__(parent)
        self._name    = name
        self._patient = patient
        self._date    = date

        self.setMinimumHeight(self._ROW_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._style_normal = (
            f"background:{C['bg_card']};border:1px solid {C['border']};"
            "border-radius:3px;"
        )
        self._style_active = (
            f"background:{C['blue_dark']};border:1px solid {C['blue_light']};"
            "border-radius:3px;"
        )
        self.setStyleSheet(self._style_normal)
        self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(6)
        self._lbl_name = QLabel(name)
        self._lbl_name.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_BASE}px;font-weight:bold;background:transparent;"
        )
        top.addWidget(self._lbl_name, stretch=1)
        self._lbl_date = QLabel(date)
        self._lbl_date.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;background:transparent;"
        )
        top.addWidget(self._lbl_date)
        lay.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self._lbl_pat = QLabel(patient)
        self._lbl_pat.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;background:transparent;"
        )
        self._lbl_pat.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bottom.addWidget(self._lbl_pat)

        btn_style = _row_action_btn_style()
        self._btn_view = QPushButton(t("rep_btn_view"))
        self._btn_view.setFixedSize(self._BTN_W_VIEW, self._BTN_H)
        self._btn_view.setStyleSheet(btn_style)
        self._btn_view.setAutoDefault(False)
        self._btn_view.setDefault(False)
        self._btn_view.clicked.connect(lambda _=False, f=on_view: f())

        self._btn_print = QPushButton(t("rep_btn_print"))
        self._btn_print.setFixedSize(self._BTN_W_PRINT, self._BTN_H)
        self._btn_print.setStyleSheet(btn_style)
        self._btn_print.setAutoDefault(False)
        self._btn_print.setDefault(False)
        self._btn_print.clicked.connect(lambda _=False, f=on_print: f())

        bottom.addWidget(self._btn_view)
        bottom.addWidget(self._btn_print)
        lay.addLayout(bottom)

    def set_selected(self, yes: bool):
        self.setStyleSheet(self._style_active if yes else self._style_normal)

    def retranslate(self):
        self._btn_view.setText(t("rep_btn_view"))
        self._btn_print.setText(t("rep_btn_print"))

    def mousePressEvent(self, event):
        self._btn_view.click()  # click() поглощает сигнал внутри _btn_view
        super().mousePressEvent(event)


# ── Генератор мок-текста отчёта ───────────────────────────────────────────────

def _report_text(name: str, patient: str, date: str) -> str:
    import random
    rng    = random.Random(hash(name))
    r_pct  = round(rng.uniform(49.0, 55.0), 1)
    l_pct  = round(100.0 - r_pct, 1)
    lr     = round(l_pct / r_pct, 2)
    vd     = round(rng.uniform(0.80, 0.95), 2)
    eeli   = round(rng.uniform(0.40, 0.50), 2)
    eili   = round(rng.uniform(1.35, 1.55), 2)
    tvi    = round(eili - eeli, 2)
    rri    = round(rng.uniform(13.0, 18.0), 1)
    cov    = round(rng.uniform(48.0, 54.0), 1)
    ss     = round(rng.uniform(0.05, 0.15), 2)

    sep = "═" * 54
    lines = [
        sep,
        "   ОТЧЁТ ЭИТ — МОНИТОРИНГ ДЫХАНИЯ",
        sep,
        f"  Пациент:       {patient}",
        f"  Дата:          {date}",
        f"  Наименование:  {name}",
        "",
        "ПОКАЗАТЕЛИ ВЕНТИЛЯЦИИ",
        "─" * 54,
    ]

    ind_lines = [
        f"  Глобальная аэрация (LI):        100.0 %",
        f"  EELI:                             {eeli} а.е.",
        f"  EILI:                             {eili} а.е.",
        f"  TVi (дых. объём по импедансу):  {tvi:.2f} а.е.",
        f"  RRi (частота дыхания):          {rri} вд/мин",
        f"  CoV (центр вентиляции):         {cov} %",
        f"  Silent Spaces:                   {ss}",
        f"  Stretch Image:                   рассчитано",
    ]
    lines += ind_lines

    lines += [
        f"  Правое лёгкое (R):              {r_pct} %",
        f"  Левое лёгкое  (L):              {l_pct} %",
        f"  L/R:                             {lr}",
        f"  V/D:                             {vd}",
        "",
        "ЗАКЛЮЧЕНИЕ",
        "─" * 54,
    ]
    if rri < 12:
        verdict = "Тип дыхания: Брадипноэ"
    elif rri > 20:
        verdict = "Тип дыхания: Тахипноэ"
    else:
        verdict = "Тип дыхания: Эупноэ"
    lines += [
        f"  {verdict}",
        "  Паттерн вентиляции в пределах нормы.",
        "",
        sep,
    ]
    return "\n".join(lines)


# ── Главный экран ─────────────────────────────────────────────────────────────

class ReportsScreen(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{C['bg_main']};")

        self._selected_row: _ReportRow | None = None
        self._report_counter = len(_MOCK_REPORTS)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(10)

        # ── Прокручиваемая область ────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        outer.addWidget(scroll, stretch=1)

        content = QWidget()
        content.setStyleSheet("background:transparent;")
        scroll.setWidget(content)

        cols = QHBoxLayout(content)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(12)

        # ═══════════════════════════════
        # ЛЕВАЯ КОЛОНКА — список отчётов
        # ═══════════════════════════════
        left = QVBoxLayout()
        left.setSpacing(8)
        cols.addLayout(left, stretch=38)

        self._box_list = _SectionBox("rep_saved_reports")
        self._list_lay = self._box_list.body_layout
        self._list_lay.setSpacing(6)

        self._btn_new = QPushButton(t("rep_new_btn"))
        self._btn_new.setFixedHeight(34)
        self._btn_new.setStyleSheet(yellow_btn_style())
        self._btn_new.clicked.connect(lambda _=False: self._new_report())
        self._list_lay.addWidget(self._btn_new)

        self._rows: list[_ReportRow] = []
        self._reports: list[tuple] = list(_MOCK_REPORTS)
        for rec in self._reports:
            self._add_row(*rec)
        self._list_lay.addStretch()

        left.addWidget(self._box_list)
        left.addStretch()

        # ════════════════════════════════════════
        # ПРАВАЯ КОЛОНКА — форма + предпросмотр
        # ════════════════════════════════════════
        right = QVBoxLayout()
        right.setSpacing(10)
        cols.addLayout(right, stretch=62)

        # ── Форма ─────────────────────────────────────────────────────────────
        self._box_form = _SectionBox("rep_create_new")
        form_lay = self._box_form.body_layout
        form_lay.setSpacing(8)

        # Период
        period_row = QHBoxLayout()
        period_row.setSpacing(8)
        self._lbl_period = QLabel(t("rep_period") + ":")
        self._lbl_period.setFixedWidth(90)
        self._lbl_period.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_BASE}px;background:transparent;"
        )
        period_row.addWidget(self._lbl_period)
        self._lbl_from = QLabel(t("rep_period_from"))
        self._lbl_from.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;background:transparent;"
        )
        self._edit_from = QLineEdit("01.01.2025")
        self._edit_from.setStyleSheet(_field_style())
        self._edit_from.setFixedWidth(100)
        self._lbl_to = QLabel(t("rep_period_to"))
        self._lbl_to.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;background:transparent;"
        )
        self._edit_to = QLineEdit(datetime.datetime.now().strftime("%d.%m.%Y"))
        self._edit_to.setStyleSheet(_field_style())
        self._edit_to.setFixedWidth(100)
        for w in (self._lbl_from, self._edit_from, self._lbl_to, self._edit_to):
            period_row.addWidget(w)
        period_row.addStretch()
        form_lay.addLayout(period_row)

        # Пациент
        pat_row = QHBoxLayout()
        pat_row.setSpacing(8)
        self._lbl_pat_f = QLabel(t("rep_patient") + ":")
        self._lbl_pat_f.setFixedWidth(90)
        self._lbl_pat_f.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_BASE}px;background:transparent;"
        )
        pat_row.addWidget(self._lbl_pat_f)
        self._combo_pat = QComboBox()
        self._combo_pat.addItems(_MOCK_PATIENTS)
        self._combo_pat.setStyleSheet(_combo_style())
        self._combo_pat.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        pat_row.addWidget(self._combo_pat)
        form_lay.addLayout(pat_row)

        # Наименование
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self._lbl_rep_name = QLabel(t("rep_report_name") + ":")
        self._lbl_rep_name.setFixedWidth(90)
        self._lbl_rep_name.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_BASE}px;background:transparent;"
        )
        name_row.addWidget(self._lbl_rep_name)
        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText(
            f"Исследование ЭИТ №{self._report_counter + 1:03d}"
        )
        self._edit_name.setStyleSheet(_field_style())
        name_row.addWidget(self._edit_name)
        form_lay.addLayout(name_row)

        self._btn_generate = QPushButton(t("rep_btn_generate"))
        self._btn_generate.setFixedHeight(44)
        self._btn_generate.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_generate.setStyleSheet(yellow_btn_style())
        self._btn_generate.clicked.connect(lambda _=False: self._generate_report())
        form_lay.addWidget(self._btn_generate)

        right.addWidget(self._box_form)

        # ── Предпросмотр ──────────────────────────────────────────────────────
        self._box_preview = _SectionBox("rep_preview_title")
        preview_lay = self._box_preview.body_layout
        preview_lay.setContentsMargins(6, 6, 6, 6)

        self._preview_stack = QStackedWidget()

        empty_w = QWidget()
        empty_w.setStyleSheet("background:transparent;")
        el = QVBoxLayout(empty_w)
        el.setAlignment(Qt.AlignCenter)
        self._lbl_empty = QLabel(t("rep_preview_empty"))
        self._lbl_empty.setAlignment(Qt.AlignCenter)
        self._lbl_empty.setStyleSheet(
            f"color:{C['text_lo']};font-size:{FONT_BASE}px;background:transparent;"
        )
        el.addWidget(self._lbl_empty)
        self._preview_stack.addWidget(empty_w)   # index 0

        self._txt_preview = QTextEdit()
        self._txt_preview.setReadOnly(True)
        self._txt_preview.setFont(QFont("Courier New", FONT_BASE))
        self._txt_preview.setStyleSheet(f"""
            QTextEdit {{
                background:{C['bg_card']}; color:{C['text']};
                border:none; padding:8px;
            }}
        """)
        self._preview_stack.addWidget(self._txt_preview)  # index 1

        preview_lay.addWidget(self._preview_stack)
        self._preview_stack.setCurrentIndex(0)
        right.addWidget(self._box_preview, stretch=1)

        # ── Нижняя панель ─────────────────────────────────────────────────────
        outer.addWidget(_hsep())

        bottom = QHBoxLayout()
        bottom.setSpacing(12)

        self._btn_start = QPushButton(t("btn_start"))
        self._btn_start.setObjectName("btn_start")
        self._btn_start.setFixedHeight(52)
        self._btn_start.setMinimumWidth(100)
        bottom.addWidget(self._btn_start)
        bottom.addStretch()

        self._btn_reset = QPushButton(t("rep_btn_reset"))
        configure_action_btn(self._btn_reset, 200)
        self._btn_reset.clicked.connect(lambda _=False: self._reset())
        bottom.addWidget(self._btn_reset)

        self._btn_print_bottom = QPushButton(t("rep_btn_print"))
        configure_action_btn(self._btn_print_bottom, 140)
        self._btn_print_bottom.clicked.connect(
            lambda: self._selected_row and self._print_report(self._selected_row._name)
        )
        bottom.addWidget(self._btn_print_bottom)

        outer.addLayout(bottom)
        i18n.language_changed.connect(self.retranslate)

    # ── Вспомогательные ───────────────────────────────────────────────────────

    def _add_row(self, name: str, patient: str, date: str, num: int):
        row = _ReportRow(
            name, patient, date,
            on_view=lambda n=name, p=patient, d=date: self._view(n, p, d),
            on_print=lambda n=name: self._print_report(n),
        )
        self._rows.append(row)
        count = self._list_lay.count()
        self._list_lay.insertWidget(count - 1, row)  # before addStretch

    def _select_row(self, row: "_ReportRow | None"):
        if self._selected_row:
            self._selected_row.set_selected(False)
        self._selected_row = row
        if row:
            row.set_selected(True)

    def _view(self, name: str, patient: str, date: str):
        row = next((r for r in self._rows if r._name == name), None)
        self._select_row(row)
        self._txt_preview.setPlainText(_report_text(name, patient, date))
        self._preview_stack.setCurrentIndex(1)

    def _print_report(self, name: str):
        row = next((r for r in self._rows if r._name == name), None)
        if row:
            self._view(row._name, row._patient, row._date)

    def _new_report(self):
        self._select_row(None)
        self._preview_stack.setCurrentIndex(0)
        self._edit_name.clear()
        self._edit_name.setFocus()

    def _generate_report(self):
        self._report_counter += 1
        name    = (self._edit_name.text().strip() or
                   f"Исследование ЭИТ №{self._report_counter:03d}")
        patient = self._combo_pat.currentText()
        date    = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

        self._reports.append((name, patient, date, self._report_counter))
        self._add_row(name, patient, date, self._report_counter)

        self._edit_name.clear()
        self._edit_name.setPlaceholderText(
            f"Исследование ЭИТ №{self._report_counter + 1:03d}"
        )
        self._view(name, patient, date)

    def _reset(self):
        self._edit_from.setText("01.01.2025")
        self._edit_to.setText(datetime.datetime.now().strftime("%d.%m.%Y"))
        self._combo_pat.setCurrentIndex(0)
        self._edit_name.clear()
        self._new_report()

    # ── Перевод ───────────────────────────────────────────────────────────────

    def retranslate(self):
        self._box_list.retranslate()
        self._box_form.retranslate()
        self._box_preview.retranslate()
        self._btn_new.setText(t("rep_new_btn"))
        self._lbl_period.setText(t("rep_period") + ":")
        self._lbl_from.setText(t("rep_period_from"))
        self._lbl_to.setText(t("rep_period_to"))
        self._lbl_pat_f.setText(t("rep_patient") + ":")
        self._lbl_rep_name.setText(t("rep_report_name") + ":")
        self._btn_generate.setText(t("rep_btn_generate"))
        self._lbl_empty.setText(t("rep_preview_empty"))
        self._btn_start.setText(t("btn_start"))
        self._btn_reset.setText(t("rep_btn_reset"))
        self._btn_print_bottom.setText(t("rep_btn_print"))
        for row in self._rows:
            row.retranslate()
