"""Окно НАСТРОЙКИ ЭИТ.

Левая колонка:  Сила тока, Частота, Количество электродов, Количество поясов
Правая колонка: Цвет визуализации (2 цвета / Стандартное), Тип дыхания (Да / Нет)
Нижняя строка:  Старт | Сбросить настройки | Сохранить настройки ЭИТ-исследования
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QSpinBox, QComboBox, QFrame, QSizePolicy, QMessageBox,
)
from PySide6.QtCore import Qt
from ..styles import C, configure_action_btn, FONT_BASE, FONT_LABEL, FONT_BTN, FONT_SMALL
from ..i18n import t, i18n
from ..application import DiagnosisCatalogService, EITSettingsService
from ..domain import AcquisitionSettings


# ── Style helpers ─────────────────────────────────────────────────────────────

def _field_style() -> str:
    return f"""
        QDoubleSpinBox, QSpinBox, QComboBox {{
            background-color: {C['bg_card']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 3px;
            padding: 4px 8px;
            font-size: {FONT_BASE}px;
            min-height: 36px;
        }}
        QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {C['blue_light']}; }}
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

    def __init__(self, label_key: str, unit_key: str, control: QWidget, parent=None):
        super().__init__(parent)
        self._label_key = label_key
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

        self._edit = control
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
        self._lbl_unit.setText(t(self._unit_key))


class _ComboRow(QWidget):
    """Label / combo box whose stable values are independent of UI language."""

    def __init__(self, label_key: str, options: tuple[tuple[str, str], ...], parent=None):
        super().__init__(parent)
        self._label_key = label_key
        self._options = options
        self.setStyleSheet("background:transparent;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._lbl = QLabel(t(label_key))
        self._lbl.setStyleSheet(_label_style())
        lay.addWidget(self._lbl)
        self._combo = QComboBox()
        self._combo.setStyleSheet(_field_style())
        lay.addWidget(self._combo)
        self.retranslate()

    def value(self) -> str:
        return str(self._combo.currentData())

    def set_value(self, value: str) -> None:
        index = self._combo.findData(value)
        self._combo.setCurrentIndex(index if index >= 0 else 0)

    def retranslate(self):
        current = self.value() if self._combo.count() else None
        self._lbl.setText(t(self._label_key))
        self._combo.clear()
        for value, label_key in self._options:
            self._combo.addItem(t(label_key), value)
        if current is not None:
            self.set_value(current)


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

    def __init__(
        self,
        diagnosis_catalog: DiagnosisCatalogService | None = None,
        settings_service: EITSettingsService | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._diagnosis_catalog = diagnosis_catalog
        self._settings_service = settings_service
        settings = settings_service.current if settings_service else AcquisitionSettings()
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

        current = QDoubleSpinBox()
        current.setRange(0.5, 5.0)
        current.setSingleStep(0.1)
        current.setDecimals(1)
        frequency = QDoubleSpinBox()
        frequency.setRange(10.0, 500.0)
        frequency.setSingleStep(10.0)
        frequency.setDecimals(0)
        electrodes = QSpinBox()
        electrodes.setRange(16, 16)
        belts = QSpinBox()
        belts.setRange(1, 1)

        self._row_current = _ParamRow("eit_current_label", "eit_unit_ma", current)
        self._row_freq = _ParamRow("eit_freq_label", "eit_unit_khz", frequency)
        self._row_electrodes = _ParamRow("eit_electrodes_label", "eit_unit_pcs", electrodes)
        self._row_belts = _ParamRow("eit_belts_label", "eit_unit_pcs", belts)

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

        self._grp_diagnosis_catalog = _ToggleGroup(
            "eit_diagnosis_catalog_label", "eit_icd10", "eit_icd11",
            default=(
                "b" if diagnosis_catalog and diagnosis_catalog.classification == "ICD-11"
                else "a"
            ),
        )
        right.addWidget(self._grp_diagnosis_catalog)

        right.addStretch()

        protocol_controls = QHBoxLayout()
        protocol_controls.setSpacing(40)
        self._row_electrode_order = _ComboRow(
            "eit_electrode_order_label",
            (
                ("right_ccw", "eit_electrode_order_right_ccw"),
                ("right_cw", "eit_electrode_order_right_cw"),
                ("sternum_cw", "eit_electrode_order_sternum_cw"),
                ("sternum_ccw", "eit_electrode_order_sternum_ccw"),
            ),
        )
        self._row_measurement_sequence = _ComboRow(
            "eit_measurement_sequence_label",
            (
                ("adjacent_fixed", "eit_sequence_adjacent_fixed"),
                ("adjacent_rotating", "eit_sequence_adjacent_rotating"),
                ("adjacent_reciprocal", "eit_sequence_adjacent_reciprocal"),
                ("adjacent_reversed", "eit_sequence_adjacent_reversed"),
            ),
        )
        protocol_controls.addWidget(self._row_electrode_order, stretch=1)
        protocol_controls.addWidget(self._row_measurement_sequence, stretch=1)
        outer.addLayout(protocol_controls)
        # Гипотезы протокола остаются частью сохранённых настроек и расчётного
        # конвейера, но больше не показываются в операторском интерфейсе.
        self._row_electrode_order.hide()
        self._row_measurement_sequence.hide()

        self._load_settings(settings)

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
        self._btn_save.clicked.connect(self._save)
        bottom.addWidget(self._btn_save)

        outer.addLayout(bottom)

        i18n.language_changed.connect(self.retranslate)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _reset(self):
        dialog = QMessageBox(
            QMessageBox.Question,
            t("eit_reset_confirm_title"),
            t("eit_reset_confirm_message"),
            QMessageBox.Yes | QMessageBox.No,
            self,
        )
        dialog.setDefaultButton(QMessageBox.No)
        dialog.button(QMessageBox.Yes).setText(t("common_yes"))
        dialog.button(QMessageBox.No).setText(t("common_no"))
        answer = dialog.exec()
        if answer != QMessageBox.Yes:
            return
        defaults = (
            self._settings_service.reset()
            if self._settings_service is not None
            else AcquisitionSettings()
        )
        self._load_settings(defaults)
        self._grp_diagnosis_catalog._select("a")
        if self._diagnosis_catalog is not None:
            self._diagnosis_catalog.set_classification("ICD-10")

    def _save(self):
        settings = self._settings_from_controls()
        if self._settings_service is not None:
            self._settings_service.save(settings)
        if self._diagnosis_catalog is not None:
            classification = (
                "ICD-10" if self._grp_diagnosis_catalog._state == "a" else "ICD-11"
            )
            self._diagnosis_catalog.set_classification(classification)

    def _settings_from_controls(self) -> AcquisitionSettings:
        return AcquisitionSettings(
            injection_current_ma=self._row_current._edit.value(),
            injection_frequency_khz=self._row_freq._edit.value(),
            electrode_count=self._row_electrodes._edit.value(),
            belt_count=self._row_belts._edit.value(),
            sample_rate_hz=25.0,
            electrode_order=self._row_electrode_order.value(),
            measurement_sequence=self._row_measurement_sequence.value(),
            two_color_visualization=self._grp_color._state == "a",
            pathology_detection=self._grp_pathology._state == "a",
        )

    def _load_settings(self, settings: AcquisitionSettings) -> None:
        self._row_current._edit.setValue(settings.injection_current_ma)
        self._row_freq._edit.setValue(settings.injection_frequency_khz)
        self._row_electrodes._edit.setValue(settings.electrode_count)
        self._row_belts._edit.setValue(settings.belt_count)
        self._row_electrode_order.set_value(settings.electrode_order)
        self._row_measurement_sequence.set_value(settings.measurement_sequence)
        self._grp_color._select("a" if settings.two_color_visualization else "b")
        self._grp_pathology._select("a" if settings.pathology_detection else "b")

    # ── Retranslate ────────────────────────────────────────────────────────────

    def retranslate(self):
        for row in (self._row_current, self._row_freq,
                    self._row_electrodes, self._row_belts):
            row.retranslate()
        self._row_electrode_order.retranslate()
        self._row_measurement_sequence.retranslate()
        self._grp_color.retranslate()
        self._grp_pathology.retranslate()
        self._grp_diagnosis_catalog.retranslate()
        self._btn_start.setText(t("btn_start"))
        self._btn_reset.setText(t("eit_btn_reset"))
        self._btn_save.setText(t("eit_btn_save"))
