"""Окно ПАЦИЕНТ.

Левая колонка:  Карточка пациента
Правая колонка: Клинические данные + История исследований
Нижняя строка:  Старт | Сохранить карточку | Привязать исследование
"""

from datetime import date
from uuid import UUID

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QFrame, QScrollArea, QSizePolicy,
    QDateEdit, QDoubleSpinBox, QDialog, QDialogButtonBox, QFormLayout,
    QListWidget, QMessageBox, QCompleter, QFileDialog,
)
from PySide6.QtCore import Qt, QDate, QTimer, QStringListModel, Signal
from ..application import (
    DiagnosisCatalogService, PatientDraft, PatientService, PatientValidationError,
    StudyHistoryEntry, StudyLifecycleError, StudyLifecycleService,
    StudyPlaybackError, StudyPlaybackService, diagnosis_text, full_years,
    resolve_diagnosis, search_diagnoses,
)
from ..domain import Diagnosis, Patient, StudyStatus, VentilationDetails
from ..session_timers import fmt_duration
from ..styles import (
    C, FONT_BASE, FONT_TITLE, FONT_SMALL,
    FONT_BTN, FONT_BTN_START,
    configure_action_btn, yellow_btn_style,
)
from ..i18n import t, i18n
from ..ui_text import study_conclusion_text


# ── Style helpers ─────────────────────────────────────────────────────────────

_FIELD_MIN_H = 28
_DETAIL_BTN_H = 32
_DETAIL_BTN_W = 110


def _field_style() -> str:
    return f"""
        QLineEdit, QDateEdit, QDoubleSpinBox {{
            background-color: {C['bg_card']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 3px;
            padding: 3px 8px;
            font-size: {FONT_BASE}px;
            min-height: {_FIELD_MIN_H}px;
        }}
        QLineEdit:focus, QDateEdit:focus, QDoubleSpinBox:focus {{
            border-color: {C['blue_light']};
        }}
        QLineEdit[validationError="true"],
        QDateEdit[validationError="true"],
        QDoubleSpinBox[validationError="true"] {{
            background-color: #2a1115;
            border: 2px solid {C['alarm']};
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
        QComboBox[validationError="true"] {{
            background-color: #2a1115;
            border: 2px solid {C['alarm']};
        }}
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

    def __init__(
        self, label_key: str, widget: QWidget, *, required: bool = False, parent=None
    ):
        super().__init__(parent)
        self._label_key = label_key
        self.required = required
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)

        self._lbl = QLabel()
        self._lbl.setTextFormat(Qt.RichText)
        self._lbl.setStyleSheet(_label_style(dim=True))
        self._lbl.setWordWrap(True)
        self._lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        lay.addWidget(self._lbl)
        lay.addWidget(widget)
        self.retranslate()

    def retranslate(self):
        suffix = f'&#160;<span style="color:{C["alarm"]};">*</span>' if self.required else ""
        self._lbl.setText(f"{t(self._label_key)}{suffix}")


# ── History row ───────────────────────────────────────────────────────────────

class _HistoryRow(QWidget):
    """Single row in the study history list."""

    def __init__(
        self, date: str, status: StudyStatus, duration: str,
        conclusion: str, on_details, on_playback=None, parent=None,
    ):
        super().__init__(parent)
        self._status = status
        self._duration = duration
        self._conclusion = conclusion
        self.setFixedHeight(40)
        self.setStyleSheet(f"""
            background-color: {C['bg_card']};
            border: 1px solid {C['border']};
            border-radius: 3px;
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 8, 4)
        lay.setSpacing(10)

        self._lbl = QLabel()
        self._lbl.setStyleSheet(f"color:{C['text']}; font-size:{FONT_BASE}px; background:transparent;")
        lay.addWidget(self._lbl, stretch=1)

        lbl_date = QLabel(date)
        lbl_date.setFixedWidth(80)
        lbl_date.setAlignment(Qt.AlignCenter)
        lbl_date.setStyleSheet(f"color:{C['text_dim']}; font-size:{FONT_SMALL}px; background:transparent;")
        lay.addWidget(lbl_date)

        self._btn_playback = QPushButton(t("pat_playback"))
        self._btn_playback.setFixedSize(_DETAIL_BTN_W, _DETAIL_BTN_H)
        self._btn_playback.setStyleSheet(_detail_btn_style())
        self._btn_playback.setVisible(on_playback is not None)
        if on_playback is not None:
            self._btn_playback.clicked.connect(on_playback)
        lay.addWidget(self._btn_playback)

        btn = QPushButton(t("pat_details"))
        btn.setFixedSize(_DETAIL_BTN_W, _DETAIL_BTN_H)
        btn.setStyleSheet(_detail_btn_style())
        btn.clicked.connect(on_details)
        lay.addWidget(btn)
        self._btn = btn
        self.retranslate()

    def retranslate(self):
        self._lbl.setText(
            f"{t('study_status_' + self._status.value)} · "
            f"{self._duration} · {self._conclusion}"
        )
        self._btn.setText(t("pat_details"))
        self._btn_playback.setText(t("pat_playback"))


class _DiagnosisDialog(QDialog):
    def __init__(self, classification: str, selected: Diagnosis | None, parent=None):
        super().__init__(parent)
        self._classification = classification
        self.setWindowTitle(f"{t('pat_icd_dialog_title')} — {classification}")
        self.resize(560, 380)
        layout = QVBoxLayout(self)
        self._search = QLineEdit()
        self._search.setPlaceholderText(t("pat_icd_search"))
        self._search.setStyleSheet(_field_style())
        self._list = QListWidget()
        layout.addWidget(self._search)
        layout.addWidget(self._list, stretch=1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("common_ok"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("common_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._search.textChanged.connect(self._refresh)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._refresh("")
        if selected is not None:
            matches = self._list.findItems(selected.code, Qt.MatchStartsWith)
            if matches:
                self._list.setCurrentItem(matches[0])

    def _refresh(self, query: str) -> None:
        self._list.clear()
        for item in search_diagnoses(query, self._classification):
            self._list.addItem(diagnosis_text(item, i18n.lang))
        if self._list.count():
            self._list.setCurrentRow(0)

    def selected_diagnosis(self) -> Diagnosis | None:
        item = self._list.currentItem()
        return (
            resolve_diagnosis(item.text(), self._classification)
            if item is not None else None
        )


class _VentilationDialog(QDialog):
    def __init__(self, details: VentilationDetails, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("pat_ivl_dialog_title"))
        form = QFormLayout(self)
        self._mode = QComboBox()
        self._mode.addItems(("VCV", "PCV", "SIMV", "CPAP", "BiPAP"))
        self._fio2 = QDoubleSpinBox()
        self._fio2.setRange(21.0, 100.0)
        self._fio2.setSuffix(" %")
        self._peep = QDoubleSpinBox()
        self._peep.setRange(0.0, 50.0)
        self._peep.setSuffix(" cmH₂O")
        if details.mode:
            self._mode.setCurrentText(details.mode)
        self._fio2.setValue(details.fio2_percent or 21.0)
        self._peep.setValue(details.peep_cmh2o or 5.0)
        form.addRow(t("pat_ivl_mode"), self._mode)
        form.addRow(t("pat_ivl_fio2"), self._fio2)
        form.addRow(t("pat_ivl_peep"), self._peep)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(t("common_ok"))
        buttons.button(QDialogButtonBox.Cancel).setText(t("common_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def details(self) -> VentilationDetails:
        return VentilationDetails(
            enabled=True,
            mode=self._mode.currentText(),
            fio2_percent=self._fio2.value(),
            peep_cmh2o=self._peep.value(),
        )


# ── Patient screen ────────────────────────────────────────────────────────────

class PatientScreen(QWidget):

    playback_started = Signal()

    def __init__(
        self,
        patient_service: PatientService | None = None,
        study_repository=None,
        diagnosis_catalog: DiagnosisCatalogService | None = None,
        study_lifecycle: StudyLifecycleService | None = None,
        playback_service: StudyPlaybackService | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._patient_service = patient_service
        self._study_repository = study_repository
        self._diagnosis_catalog = diagnosis_catalog
        self._study_lifecycle = study_lifecycle
        self._playback_service = playback_service
        self._current_patient_id: UUID | None = None
        self._main_diagnosis: Diagnosis | None = None
        self._accompanying_diagnoses: tuple[Diagnosis, ...] = ()
        self._ventilation = VentilationDetails()
        self._dirty = False
        self._loading = False
        self._completion_ids: dict[str, UUID] = {}
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
        self._fr_last  = _FieldRow("pat_last_name",   self._e_last, required=True)
        self._fr_first = _FieldRow("pat_first_name",  self._e_first, required=True)
        self._fr_patr  = _FieldRow("pat_patronymic",  self._e_patr)
        r1.addWidget(self._fr_last);  r1.addWidget(self._fr_first);  r1.addWidget(self._fr_patr)
        card_lay.addLayout(r1)

        # Row 2: Дата рождения | Пол | Номер истории болезни
        r2 = QHBoxLayout(); r2.setSpacing(8)
        self._e_dob = QDateEdit()
        self._e_dob.setCalendarPopup(True)
        self._e_dob.setDisplayFormat("dd.MM.yyyy")
        self._e_dob.setDate(QDate.currentDate())
        self._e_dob.setMaximumDate(QDate.currentDate())
        self._e_dob.setMinimumDate(QDate(1900, 1, 1))
        self._e_dob.setStyleSheet(_field_style())
        self._cmb_gender = QComboBox()
        self._cmb_gender.setStyleSheet(_combo_style())
        self._cmb_gender.addItems([t("pat_gender_m"), t("pat_gender_f")])
        self._e_record = QLineEdit(); self._e_record.setStyleSheet(_field_style())
        self._fr_dob    = _FieldRow("pat_dob",        self._e_dob, required=True)
        self._fr_gender = _FieldRow("pat_gender",     self._cmb_gender, required=True)
        self._fr_record = _FieldRow("pat_record_num", self._e_record, required=True)
        r2.addWidget(self._fr_dob, stretch=2)
        r2.addWidget(self._fr_gender, stretch=1)
        r2.addWidget(self._fr_record, stretch=2)
        card_lay.addLayout(r2)

        # Row 3: Вес | Рост | ID
        r3 = QHBoxLayout(); r3.setSpacing(8)
        self._e_weight = self._number_field(0.5, 500.0, 1)
        self._e_height = self._number_field(20.0, 250.0, 1)
        self._e_id     = QLineEdit(); self._e_id.setStyleSheet(_field_style())
        self._fr_weight = _FieldRow("pat_weight", self._e_weight, required=True)
        self._fr_height = _FieldRow("pat_height", self._e_height, required=True)
        self._fr_id     = _FieldRow("pat_id",     self._e_id, required=True)
        r3.addWidget(self._fr_weight); r3.addWidget(self._fr_height); r3.addWidget(self._fr_id)
        card_lay.addLayout(r3)

        # Row 4: Охват грудной клетки | Полных лет | Присвоить код ID
        r4 = QHBoxLayout(); r4.setSpacing(8)
        self._e_chest = self._number_field(20.0, 250.0, 1)
        self._e_age   = QLineEdit(); self._e_age.setReadOnly(True)
        self._e_age.setStyleSheet(_field_style())
        self._btn_assign_id = QPushButton(t("pat_assign_id"))
        self._btn_assign_id.setFixedHeight(_FIELD_MIN_H + 4)
        self._btn_assign_id.setStyleSheet(yellow_btn_style())
        self._fr_chest = _FieldRow("pat_chest", self._e_chest, required=True)
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
        self._history_layout = hist_lay
        self._btn_import_json = QPushButton(t("pat_import_eit_json"))
        self._btn_import_json.setStyleSheet(_detail_btn_style())
        self._btn_import_json.setToolTip(t("pat_import_eit_json_hint"))
        self._btn_import_json.clicked.connect(self._open_json_recording)
        hist_lay.addWidget(self._btn_import_json)
        self._history_empty = QLabel(t("pat_history_empty"))
        self._history_empty.setStyleSheet(_label_style(dim=True))
        hist_lay.addWidget(self._history_empty)

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

        self._btn_assign_id.clicked.connect(self._assign_id)
        self._btn_save.clicked.connect(self._save)
        self._btn_detail1.clicked.connect(lambda: self._choose_diagnosis(True))
        self._btn_detail2.clicked.connect(lambda: self._choose_diagnosis(False))
        self._btn_detail3.clicked.connect(self._edit_ventilation)
        self._btn_link.clicked.connect(self._link_study)
        self._e_dob.dateChanged.connect(self._update_age)
        self._validation_widgets = {
            "family_name": self._e_last,
            "given_name": self._e_first,
            "middle_name": self._e_patr,
            "date_of_birth": self._e_dob,
            "sex": self._cmb_gender,
            "medical_record_number": self._e_record,
            "external_id": self._e_id,
            "weight_kg": self._e_weight,
            "height_cm": self._e_height,
            "chest_circumference_cm": self._e_chest,
            "main_diagnosis": self._e_main_diag,
            "accompanying_diagnoses": self._e_acc_diag,
        }
        self._connect_validation_feedback()
        self._connect_dirty_tracking()
        self._configure_patient_search()
        self._update_age()
        self.refresh_diagnosis_catalog()
        self._dirty = False

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
        if state == "no":
            self._ventilation = VentilationDetails()
        elif not self._ventilation.enabled:
            self._ventilation = VentilationDetails(enabled=True)
        self._mark_dirty()

    @staticmethod
    def _number_field(minimum: float, maximum: float, decimals: int) -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(0.0, maximum)
        field.setDecimals(decimals)
        field.setSpecialValueText("")
        field.setStyleSheet(_field_style())
        field.setProperty("validMinimum", minimum)
        return field

    @staticmethod
    def _optional_number(field: QDoubleSpinBox) -> float | None:
        return None if field.value() == field.minimum() else field.value()

    def _connect_dirty_tracking(self) -> None:
        for field in (self._e_last, self._e_first, self._e_patr, self._e_record,
                      self._e_id, self._e_main_diag, self._e_acc_diag):
            field.textChanged.connect(self._mark_dirty)
        for field in (self._e_weight, self._e_height, self._e_chest):
            field.valueChanged.connect(self._mark_dirty)
        self._e_dob.dateChanged.connect(self._mark_dirty)
        self._cmb_gender.currentIndexChanged.connect(self._mark_dirty)

    def _connect_validation_feedback(self) -> None:
        for field in self._validation_widgets.values():
            if isinstance(field, QLineEdit):
                signal = field.textChanged
            elif isinstance(field, QDateEdit):
                signal = field.dateChanged
            elif isinstance(field, QComboBox):
                signal = field.currentIndexChanged
            else:
                signal = field.valueChanged
            signal.connect(
                lambda *_args, current=field: self._set_validation_error(current, None)
            )

    @staticmethod
    def _set_validation_error(field: QWidget, message: str | None) -> None:
        field.setProperty("validationError", bool(message))
        field.setToolTip(message or "")
        field.style().unpolish(field)
        field.style().polish(field)
        field.update()

    def _show_validation_errors(self, errors: dict[str, str]) -> None:
        for field in set(self._validation_widgets.values()):
            self._set_validation_error(field, None)
        for name, message in errors.items():
            if name == "patient":
                for duplicate_field in (self._e_id, self._e_record):
                    self._set_validation_error(
                        duplicate_field, t("pat_error_duplicate")
                    )
                continue
            field = self._validation_widgets.get(name)
            if field is not None:
                self._set_validation_error(
                    field, self._localized_validation_message(name, message)
                )

    @staticmethod
    def _localized_validation_message(name: str, message: str) -> str:
        if name in {"family_name", "given_name"}:
            key = (
                "pat_error_required"
                if "required" in message.lower()
                else "pat_error_name_format"
            )
        else:
            key = {
                "middle_name": "pat_error_name_format",
                "sex": "pat_error_required",
                "weight_kg": "pat_error_weight_range",
                "height_cm": "pat_error_height_range",
                "chest_circumference_cm": "pat_error_chest_range",
                "main_diagnosis": "pat_invalid_diagnosis",
                "accompanying_diagnoses": "pat_invalid_diagnosis",
            }.get(name)
        if name == "date_of_birth":
            key = (
                "pat_error_birth_future"
                if "future" in message.lower()
                else "pat_error_required"
            )
        elif name == "external_id":
            key = (
                "pat_error_duplicate"
                if "already exists" in message.lower()
                else "pat_error_id_format"
            )
        elif name == "medical_record_number":
            key = (
                "pat_error_duplicate"
                if "already exists" in message.lower()
                else "pat_error_record_format"
            )
        return t(key or "pat_error_invalid_value")

    def _mark_dirty(self, *_args) -> None:
        if not self._loading:
            self._dirty = True

    @property
    def has_unsaved_changes(self) -> bool:
        return self._dirty

    def confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        dialog = self._create_unsaved_changes_dialog()
        answer = dialog.exec()
        return answer == QMessageBox.Discard

    def _create_unsaved_changes_dialog(self) -> QMessageBox:
        dialog = QMessageBox(
            QMessageBox.Question,
            t("pat_unsaved_title"),
            t("pat_unsaved_message"),
            QMessageBox.Discard | QMessageBox.Cancel,
            self,
        )
        dialog.setDefaultButton(QMessageBox.Cancel)
        dialog.button(QMessageBox.Discard).setText(t("pat_unsaved_discard"))
        dialog.button(QMessageBox.Cancel).setText(t("pat_unsaved_cancel"))
        return dialog

    def _update_age(self, *_args) -> None:
        selected = self._e_dob.date().toPython()
        try:
            self._e_age.setText(str(full_years(selected, date.today())))
        except ValueError:
            self._e_age.clear()

    def _assign_id(self) -> None:
        if self._patient_service is None:
            return
        self._e_id.setText(self._patient_service.assign_external_id())

    def _draft(self) -> PatientDraft:
        main = self._resolve_field_diagnosis(
            self._e_main_diag.text(), self._main_diagnosis
        )
        previous_accompanying = (
            self._accompanying_diagnoses[0] if self._accompanying_diagnoses else None
        )
        accompanying = self._resolve_field_diagnosis(
            self._e_acc_diag.text(), previous_accompanying
        )
        if self._e_main_diag.text().strip() and main is None:
            raise PatientValidationError({"main_diagnosis": t("pat_invalid_diagnosis")})
        if self._e_acc_diag.text().strip() and accompanying is None:
            raise PatientValidationError({"accompanying_diagnoses": t("pat_invalid_diagnosis")})
        return PatientDraft(
            external_id=self._e_id.text(),
            medical_record_number=self._e_record.text(),
            family_name=self._e_last.text(),
            given_name=self._e_first.text(),
            middle_name=self._e_patr.text(),
            date_of_birth=self._e_dob.date().toPython(),
            sex="male" if self._cmb_gender.currentIndex() == 0 else "female",
            weight_kg=self._optional_number(self._e_weight),
            height_cm=self._optional_number(self._e_height),
            chest_circumference_cm=self._optional_number(self._e_chest),
            main_diagnosis=main,
            accompanying_diagnoses=(accompanying,) if accompanying else (),
            ventilation=self._ventilation,
        )

    def _resolve_field_diagnosis(
        self, text: str, selected: Diagnosis | None
    ) -> Diagnosis | None:
        stripped = text.strip()
        if not stripped:
            return None
        if selected is not None and stripped == self._diagnosis_text(selected):
            return selected
        return resolve_diagnosis(stripped, self._active_classification())

    def _diagnosis_text(self, diagnosis: Diagnosis) -> str:
        current = resolve_diagnosis(diagnosis.code, diagnosis.classification) or diagnosis
        return diagnosis_text(current, i18n.lang)

    def _active_classification(self) -> str:
        return (
            self._diagnosis_catalog.classification
            if self._diagnosis_catalog is not None else "ICD-10"
        )

    def refresh_diagnosis_catalog(self) -> None:
        placeholder_key = (
            "pat_icd_code_11" if self._active_classification() == "ICD-11"
            else "pat_icd_code_10"
        )
        self._e_main_diag.setPlaceholderText(t(placeholder_key))
        self._e_acc_diag.setPlaceholderText(t(placeholder_key))

    def _save(self) -> None:
        if self._patient_service is None:
            return
        try:
            patient = self._patient_service.save(
                self._draft(), patient_id=self._current_patient_id
            )
        except PatientValidationError as exc:
            self._show_validation_errors(exc.field_errors)
            QMessageBox.warning(self, t("pat_validation_title"), t("pat_validation_message"))
            return
        self._show_validation_errors({})
        self._current_patient_id = patient.id
        if self._study_lifecycle is not None:
            self._study_lifecycle.select_patient(patient.id)
        self._dirty = False
        QMessageBox.information(self, t("pat_saved_title"), t("pat_saved_message"))
        self._refresh_completions("")

    def _choose_diagnosis(self, main: bool) -> None:
        selected = self._main_diagnosis if main else (
            self._accompanying_diagnoses[0] if self._accompanying_diagnoses else None
        )
        classification = self._active_classification()
        if selected is not None and selected.classification != classification:
            selected = None
        dialog = _DiagnosisDialog(classification, selected, self)
        if dialog.exec() != QDialog.Accepted:
            return
        diagnosis = dialog.selected_diagnosis()
        if diagnosis is None:
            return
        text = self._diagnosis_text(diagnosis)
        if main:
            self._main_diagnosis = diagnosis
            self._e_main_diag.setText(text)
        else:
            self._accompanying_diagnoses = (diagnosis,)
            self._e_acc_diag.setText(text)

    def _edit_ventilation(self) -> None:
        if self._ivl_state != "yes":
            return
        dialog = _VentilationDialog(self._ventilation, self)
        if dialog.exec() == QDialog.Accepted:
            self._ventilation = dialog.details()
            self._mark_dirty()

    def _configure_patient_search(self) -> None:
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._run_search)
        self._search_source: QLineEdit | None = None
        self._search_models: list[QStringListModel] = []
        for field in (self._e_last, self._e_first, self._e_id, self._e_record):
            model = QStringListModel(self)
            completer = QCompleter(model, field)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            completer.activated.connect(self._select_completion)
            field.setCompleter(completer)
            field.textEdited.connect(lambda _text, source=field: self._schedule_search(source))
            self._search_models.append(model)

    def _schedule_search(self, source: QLineEdit) -> None:
        self._search_source = source
        self._search_timer.start()

    def _run_search(self) -> None:
        if self._patient_service is None or self._search_source is None:
            return
        self._refresh_completions(self._search_source.text())

    def _refresh_completions(self, query: str) -> None:
        if self._patient_service is None:
            return
        self._completion_ids.clear()
        values: list[str] = []
        for patient in self._patient_service.search(query, limit=50):
            display = self._patient_display(patient)
            self._completion_ids[display] = patient.id
            values.append(display)
        for model in self._search_models:
            model.setStringList(values)

    @staticmethod
    def _patient_display(patient: Patient) -> str:
        name = " ".join(filter(None, (patient.family_name, patient.given_name, patient.middle_name)))
        return f"{name} | {patient.external_id or '—'} | {patient.medical_record_number or '—'}"

    def _select_completion(self, display: str) -> None:
        if self._patient_service is None:
            return
        patient_id = self._completion_ids.get(display)
        if patient_id is None:
            return
        patient = self._patient_service.repository.get(patient_id)
        if patient is not None:
            self.load_patient(patient)

    def load_patient(self, patient: Patient) -> None:
        if self._study_lifecycle is not None:
            try:
                self._study_lifecycle.select_patient(patient.id)
            except StudyLifecycleError:
                QMessageBox.warning(
                    self, t("study_action_error_title"), t("study_active_other_patient")
                )
                return
        self._loading = True
        try:
            self._current_patient_id = patient.id
            self._e_last.setText(patient.family_name or "")
            self._e_first.setText(patient.given_name or "")
            self._e_patr.setText(patient.middle_name or "")
            if patient.date_of_birth:
                self._e_dob.setDate(QDate(patient.date_of_birth.year, patient.date_of_birth.month, patient.date_of_birth.day))
            self._cmb_gender.setCurrentIndex(1 if patient.sex == "female" else 0)
            self._e_record.setText(patient.medical_record_number or "")
            self._e_id.setText(patient.external_id or "")
            self._e_weight.setValue(patient.weight_kg or 0.0)
            self._e_height.setValue(patient.height_cm or 0.0)
            self._e_chest.setValue(patient.chest_circumference_cm or 0.0)
            self._main_diagnosis = patient.main_diagnosis
            self._accompanying_diagnoses = patient.accompanying_diagnoses
            self._e_main_diag.setText(
                self._diagnosis_text(patient.main_diagnosis)
                if patient.main_diagnosis else ""
            )
            accompanying = patient.accompanying_diagnoses[0] if patient.accompanying_diagnoses else None
            self._e_acc_diag.setText(
                self._diagnosis_text(accompanying) if accompanying else ""
            )
            self._ventilation = patient.ventilation
            self._set_ivl("yes" if patient.ventilation.enabled else "no")
            self._load_history(patient.id)
            self._update_age()
        finally:
            self._loading = False
            self._dirty = False
            self._show_validation_errors({})

    def _link_study(self) -> None:
        if self._study_lifecycle is None or self._current_patient_id is None:
            QMessageBox.warning(
                self, t("study_action_error_title"), t("study_select_patient_first")
            )
            return
        try:
            self._study_lifecycle.select_patient(self._current_patient_id)
            study = self._study_lifecycle.create_study()
            self._study_lifecycle.prepare()
        except StudyLifecycleError:
            QMessageBox.warning(
                self, t("study_action_error_title"), t("study_finish_current_first")
            )
            return
        self._load_history(study.patient_id)
        QMessageBox.information(
            self, t("study_linked_title"), t("study_linked_message")
        )

    def _load_history(self, patient_id: UUID) -> None:
        for row in self._history_rows:
            self._history_layout.removeWidget(row)
            row.deleteLater()
        self._history_rows.clear()
        entries = (
            self._study_lifecycle.list_history(patient_id)
            if self._study_lifecycle is not None else ()
        )
        self._history_empty.setVisible(not entries)
        for entry in entries:
            study = entry.study
            local_date = study.created_at_utc.astimezone().strftime("%d.%m.%Y")
            conclusion = self._conclusion_text(study.conclusion)
            row = _HistoryRow(
                local_date,
                study.status,
                fmt_duration(int(entry.duration_seconds)),
                conclusion,
                lambda _checked=False, item=entry: self._open_study_details(item),
                (lambda _checked=False, item=entry: self._start_playback(item))
                if entry.study.status is StudyStatus.COMPLETED and entry.session is not None
                else None,
            )
            self._history_rows.append(row)
            self._history_layout.addWidget(row)

    def refresh_history(self) -> None:
        if self._current_patient_id is not None:
            self._load_history(self._current_patient_id)

    @staticmethod
    def _conclusion_text(conclusion: str | None) -> str:
        return study_conclusion_text(conclusion)

    def _open_study_details(self, entry: StudyHistoryEntry) -> None:
        if self._study_lifecycle is not None:
            try:
                self._study_lifecycle.open_study(entry.study.id)
            except StudyLifecycleError:
                QMessageBox.warning(
                    self, t("study_action_error_title"), t("study_invalid_transition")
                )
                return
        created = entry.study.created_at_utc.astimezone().strftime("%d.%m.%Y %H:%M")
        text = "\n".join((
            f"{t('study_details_date')}: {created}",
            f"{t('study_details_duration')}: {fmt_duration(int(entry.duration_seconds))}",
            f"{t('study_details_status')}: {t('study_status_' + entry.study.status.value)}",
            f"{t('study_details_conclusion')}: {self._conclusion_text(entry.study.conclusion)}",
            f"{t('study_details_author')}: {entry.study.author or '—'}",
        ))
        QMessageBox.information(self, t("study_details_title"), text)

    def _start_playback(self, entry: StudyHistoryEntry) -> None:
        if self._playback_service is None or entry.session is None:
            return
        try:
            self._playback_service.open(entry.study.id, entry.session.id)
        except (RuntimeError, OSError, ValueError):
            QMessageBox.warning(
                self, t("study_action_error_title"), t("study_playback_unavailable")
            )
            return
        self.playback_started.emit()

    def _open_json_recording(self) -> None:
        if self._playback_service is None:
            return
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            t("pat_import_eit_json"),
            "",
            t("pat_import_eit_json_filter"),
        )
        if not path:
            return
        try:
            self._playback_service.open_file(path)
        except (RuntimeError, OSError, ValueError):
            QMessageBox.warning(
                self,
                t("study_action_error_title"),
                t("pat_import_eit_json_error"),
            )
            return
        self.playback_started.emit()

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
        self.refresh_diagnosis_catalog()
        if self._main_diagnosis is not None:
            blocked = self._e_main_diag.blockSignals(True)
            self._e_main_diag.setText(self._diagnosis_text(self._main_diagnosis))
            self._e_main_diag.blockSignals(blocked)
        if self._accompanying_diagnoses:
            blocked = self._e_acc_diag.blockSignals(True)
            self._e_acc_diag.setText(
                self._diagnosis_text(self._accompanying_diagnoses[0])
            )
            self._e_acc_diag.blockSignals(blocked)
        self._lbl_ivl.setText(t("pat_ivl"))
        self._btn_ivl_yes.setText(t("pat_yes"))
        self._btn_ivl_no.setText(t("pat_no"))
        for b in (self._btn_detail1, self._btn_detail2, self._btn_detail3):
            b.setText(t("pat_details"))

        for row in self._history_rows:
            row.retranslate()
        self._history_empty.setText(t("pat_history_empty"))
        self._btn_import_json.setText(t("pat_import_eit_json"))
        self._btn_import_json.setToolTip(t("pat_import_eit_json_hint"))

        self._btn_save.setText(t("pat_save_card"))
        self._btn_link.setText(t("pat_link_study"))
