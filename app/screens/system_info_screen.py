"""Системная информация — Table 7.5 of spec (12 parameters).

Row 11 (Date and time) updates every second via QTimer.
Row 12 (Interface language) has an inline «Change language» button.
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QDialog, QButtonGroup, QRadioButton, QTabWidget, QGridLayout,
    QCheckBox, QSpinBox, QGroupBox, QScrollArea, QComboBox, QStackedWidget,
    QSlider, QColorDialog,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QValidator

from ..config import AppConfig, DataMode
from ..application import (
    INTERFACE_ELEMENTS,
    INTERFACE_TABS,
    REQUIRED_INTERFACE_TABS,
    MAX_GRAPH_DISPLAY_PERIOD_SECONDS,
    MAX_ROI_COUNT,
    MIN_GRAPH_DISPLAY_PERIOD_SECONDS,
    MIN_PEEP_ANALYSIS_INTERVAL_SECONDS,
    MAX_PEEP_ANALYSIS_INTERVAL_SECONDS,
    MIN_PEEP_SILENT_THRESHOLD_PERCENT,
    MAX_PEEP_SILENT_THRESHOLD_PERCENT,
    MIN_TREND_DECIMAL_PLACES,
    MAX_TREND_DECIMAL_PLACES,
    DEFAULT_APPLICATION_BACKGROUND_COLOR,
    EngineeringSettings,
    EngineeringSettingsService,
)
from ..styles import (
    C, FONT_BASE, FONT_SMALL, FONT_TITLE, FONT_LABEL, FONT_VALUE, FONT_BTN,
)
from ..i18n import t, i18n, LANGUAGES
from ..widgets.section_profile_editor import SectionProfileEditor


# ── Language selector dialog ──────────────────────────────────────────────────


class _EvenRoiSpinBox(QSpinBox):
    """Numeric editor that only accepts even ROI counts from 2 through 20."""

    def validate(self, text: str, position: int):
        stripped = text.strip()
        if not stripped:
            return QValidator.Intermediate, text, position
        try:
            value = int(stripped)
        except ValueError:
            return QValidator.Invalid, text, position
        state = (
            QValidator.Acceptable
            if 2 <= value <= 20 and value % 2 == 0
            else QValidator.Invalid
        )
        return state, text, position

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
_INTERFACE_TAB_KEYS = {
    "main": "nav_main",
    "express_monitoring": "nav_express_monitoring",
    "patient": "nav_patient",
    "trends": "nav_trends",
    "analysis": "nav_analysis",
    "peep": "nav_peep",
    "eit_settings": "nav_eit_settings",
    "reports": "nav_reports",
    "export": "nav_export",
    "service": "nav_service",
    "system": "nav_system",
    "debug": "nav_debug",
}
_ELEMENT_LABEL_KEYS = {
    element: "sys_element_" + element.replace(".", "_")
    for elements in INTERFACE_ELEMENTS.values()
    for element in elements
}

_ENGINEERING_REFERENCE_ITEMS = (
    ("marker_chart_prefix", "", "sys_reference_event"),
    ("", "ΔZ", "sys_reference_delta_z"),
    ("", "σ", "sys_reference_conductivity"),
    ("", "EELI", "sys_reference_eeli"),
    ("", "EILI", "sys_reference_eili"),
    ("", "TVi", "sys_reference_tvi"),
    ("", "MVi", "sys_reference_mvi"),
    ("", "RR / ЧД", "sys_reference_rr"),
    ("", "R/L", "sys_reference_rl"),
    ("", "V/D", "sys_reference_vd"),
    ("", "ROI", "sys_reference_roi"),
    ("", "N, %", "sys_reference_n_percent"),
    ("", "PEEP", "sys_reference_peep"),
    ("", "RTS", "sys_reference_rts"),
    ("", "CoV", "sys_reference_cov"),
    ("", "DSS / NSS", "sys_reference_silent_spaces"),
    ("", "FLS", "sys_reference_fls"),
    ("", "BB / TB", "sys_reference_trend_points"),
    ("", "AU / a.u.", "sys_reference_au"),
)

_BASE_TREND_VISIBILITY_ITEMS = (
    ("eeli_au", "EELI"),
    ("eili_au", "EILI"),
    ("tvi_au", "TVi"),
    ("mli_au", "MLI"),
    ("mvi_au_per_min", "MVi"),
    ("rr_bpm", "RR / ЧД"),
    ("right_left_ratio", "R/L"),
    ("ventral_dorsal_ratio", "V/D"),
    ("right_percent", "R, %"),
    ("left_percent", "L, %"),
)


def _trend_visibility_items(roi_count: int) -> tuple[tuple[str, str], ...]:
    return _BASE_TREND_VISIBILITY_ITEMS + tuple(
        item
        for index in range(1, roi_count + 1)
        for item in (
            (f"roi_{index}_tvi_au", f"TVi ROI {index}"),
            (f"roi_{index}_percent", f"ROI {index}, %"),
        )
    )


def _aeration_visibility_items(roi_count: int) -> tuple[tuple[str, str], ...]:
    return (("total_percent", "T, %"),) + _trend_visibility_items(roi_count)


def _single_line_tab_text(tab: str) -> str:
    return t(_INTERFACE_TAB_KEYS[tab]).replace("\n", " ")


def _engineering_tabs_style() -> str:
    return f"""
        QTabWidget::pane {{
            border: 1px solid {C['border']};
            border-radius: 6px;
            top: -1px;
            background: {C['bg_main']};
        }}
        QTabBar::tab {{
            background: {C['bg_nav']};
            color: {C['text_dim']};
            border: 1px solid {C['border']};
            border-bottom: none;
            padding: 9px 10px;
            min-width: 105px;
            min-height: 24px;
            font-size: {FONT_BASE}px;
            font-weight: 500;
        }}
        QTabBar::tab:first {{ border-top-left-radius: 6px; }}
        QTabBar::tab:last {{ border-top-right-radius: 6px; }}
        QTabBar::tab:selected {{
            background: {C['blue']};
            color: white;
            font-weight: bold;
        }}
        QTabBar::tab:hover:!selected {{
            background: {C['nav_hover']};
            color: {C['text']};
        }}
    """


def _visibility_checkbox_style() -> str:
    return f"""
        QCheckBox {{
            background: {C['bg_card']};
            color: {C['text']};
            border: 1px solid {C['border']};
            border-radius: 6px;
            padding: 8px 12px;
            spacing: 10px;
            min-height: 28px;
            font-size: {FONT_SMALL}px;
        }}
        QCheckBox:hover {{ border-color: {C['blue_light']}; }}
        QCheckBox:checked {{
            background: {C['nav_hover']};
            border-color: {C['blue_light']};
        }}
        QCheckBox:disabled {{
            background: {C['bg_panel']};
            color: {C['text_dim']};
            border-color: {C['border']};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
        }}
    """


def _visibility_combo_style() -> str:
    return f"""
        QComboBox {{
            background: {C['bg_card']};
            color: {C['text']};
            border: 1px solid {C['blue_light']};
            border-radius: 6px;
            padding: 8px 12px;
            min-height: 30px;
            font-size: {FONT_BASE}px;
        }}
        QComboBox:hover {{ background: {C['nav_hover']}; }}
        QComboBox::drop-down {{ border: none; width: 30px; }}
        QComboBox QAbstractItemView {{
            background: {C['bg_panel']};
            color: {C['text']};
            border: 1px solid {C['border_light']};
            selection-background-color: {C['blue']};
            padding: 4px;
        }}
    """


# ── System info screen ────────────────────────────────────────────────────────

class SystemInfoScreen(QWidget):
    """System information table — 12 parameters from spec Table 7.5."""

    def __init__(
        self,
        config: AppConfig | None = None,
        engineering_settings: EngineeringSettingsService | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config or AppConfig.from_env()
        self._engineering_settings = engineering_settings
        self.setStyleSheet(f"background-color:{C['bg_main']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 14, 24, 14)
        outer.setSpacing(10)

        # Screen title
        self._lbl_title = QLabel(t("screen_system"))
        self._lbl_title.setAlignment(Qt.AlignCenter)
        self._lbl_title.setStyleSheet(
            f"color:{C['text']};font-size:22px;font-weight:bold;background:transparent;"
        )
        outer.addWidget(self._lbl_title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['border']};")
        outer.addWidget(sep)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_engineering_tabs_style())
        self._info_tab = QWidget()
        self._engineering_tab = QWidget()
        self._tabs.addTab(self._info_tab, t("sys_tab_information"))
        self._tabs.addTab(self._engineering_tab, t("sys_tab_engineering"))
        outer.addWidget(self._tabs, stretch=1)

        info_lay = QVBoxLayout(self._info_tab)
        info_lay.setContentsMargins(0, 12, 0, 0)
        info_lay.setSpacing(0)

        # Table container
        table = QWidget()
        table.setStyleSheet("background:transparent;")
        table_lay = QVBoxLayout(table)
        table_lay.setContentsMargins(0, 0, 0, 0)
        table_lay.setSpacing(0)
        self._info_scroll = QScrollArea()
        self._info_scroll.setWidgetResizable(True)
        self._info_scroll.setFrameShape(QFrame.NoFrame)
        self._info_scroll.setWidget(table)
        info_lay.addWidget(self._info_scroll)

        # Header row
        self._lbl_h_num, self._lbl_h_param, self._lbl_h_value = \
            self._build_header(table_lay)

        # Data rows
        self._param_lbls: list[tuple[str, QLabel]] = []
        self._val_lbls: list[tuple[str, QLabel]] = []   # (i18n_key or "", label)
        self._datetime_lbl: QLabel | None = None
        self._lang_val_lbl: QLabel | None = None
        self._device_model_lbl: QLabel | None = None
        self._btn_change: QPushButton | None = None

        for i, row in enumerate(_ROWS):
            lbl_key, val_key, val_is_i18n, row_type = row
            self._build_row(table_lay, i + 1, lbl_key, val_key,
                            val_is_i18n, row_type, even=(i % 2 == 0))

        self._build_engineering_tab()

        # Datetime ticker
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

        i18n.language_changed.connect(self.retranslate)

    def _build_engineering_tab(self) -> None:
        outer = QVBoxLayout(self._engineering_tab)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

        self._engineering_sections = QTabWidget()
        self._engineering_sections.setStyleSheet(_engineering_tabs_style())
        self._engineering_general_tab = QWidget()
        self._engineering_trends_tab = QWidget()
        self._engineering_peep_tab = QWidget()
        self._engineering_visibility_tab = QWidget()
        self._engineering_section_tab = QWidget()
        self._engineering_appearance_tab = QWidget()
        self._engineering_reference_tab = QWidget()
        self._engineering_sections.addTab(
            self._engineering_general_tab, t("sys_engineering_tab_general")
        )
        self._engineering_sections.addTab(
            self._engineering_trends_tab, t("sys_engineering_tab_trends")
        )
        self._engineering_sections.addTab(
            self._engineering_peep_tab, t("sys_engineering_tab_peep")
        )
        self._engineering_sections.addTab(
            self._engineering_visibility_tab, t("sys_engineering_tab_visibility")
        )
        self._engineering_sections.addTab(
            self._engineering_section_tab, t("sys_engineering_tab_section")
        )
        self._engineering_sections.addTab(
            self._engineering_appearance_tab, t("sys_engineering_tab_appearance")
        )
        self._engineering_sections.addTab(
            self._engineering_reference_tab, t("sys_engineering_tab_reference")
        )
        outer.addWidget(self._engineering_sections, stretch=1)

        layout = QVBoxLayout(self._engineering_general_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        self._mode_group = QGroupBox(t("sys_engineering_modes"))
        mode_layout = QHBoxLayout(self._mode_group)
        self._mode_checks: dict[str, QCheckBox] = {}
        for mode, key in (
            ("adult", "sys_mode_adult"),
            ("infant", "sys_mode_infant"),
            ("ventilation", "sys_mode_ventilation"),
        ):
            checkbox = QCheckBox(t(key))
            checkbox.clicked.connect(
                lambda checked, selected=mode: self._validate_mode_selection(selected, checked)
            )
            mode_layout.addWidget(checkbox)
            self._mode_checks[mode] = checkbox
        mode_layout.addStretch()

        roi_row = QHBoxLayout()
        self._roi_label = QLabel(t("sys_engineering_roi_count"))
        roi_row.addWidget(self._roi_label)
        self._roi_spin = _EvenRoiSpinBox()
        self._roi_spin.setRange(2, 20)
        self._roi_spin.setSingleStep(2)
        self._roi_spin.setValue(8)
        self._roi_spin.setFixedWidth(120)
        roi_row.addWidget(self._roi_spin)
        roi_row.addStretch()
        layout.addWidget(self._mode_group)
        layout.addLayout(roi_row)

        graph_period_row = QHBoxLayout()
        self._graph_period_label = QLabel(t("sys_engineering_graph_period"))
        graph_period_row.addWidget(self._graph_period_label)
        self._graph_period_slider = QSlider(Qt.Horizontal)
        self._graph_period_slider.setObjectName("graph_period_slider")
        self._graph_period_slider.setStyleSheet(f"""
            QSlider#graph_period_slider::groove:horizontal {{
                height: 6px;
                background: {C['border_light']};
                border-radius: 3px;
            }}
            QSlider#graph_period_slider::sub-page:horizontal {{
                background: {C['blue_light']};
                border-radius: 3px;
            }}
            QSlider#graph_period_slider::add-page:horizontal {{
                background: {C['border_light']};
                border-radius: 3px;
            }}
            QSlider#graph_period_slider::handle:horizontal {{
                width: 18px;
                margin: -6px 0;
                background: {C['text']};
                border: 2px solid {C['blue_light']};
                border-radius: 9px;
            }}
            QSlider#graph_period_slider::handle:horizontal:hover {{
                background: white;
            }}
        """)
        self._graph_period_slider.setRange(
            MIN_GRAPH_DISPLAY_PERIOD_SECONDS,
            MAX_GRAPH_DISPLAY_PERIOD_SECONDS,
        )
        self._graph_period_slider.setSingleStep(1)
        self._graph_period_slider.setPageStep(10)
        self._graph_period_slider.setTickInterval(10)
        self._graph_period_slider.setTickPosition(QSlider.TicksBelow)
        self._graph_period_slider.setMinimumWidth(320)
        graph_period_row.addWidget(self._graph_period_slider, stretch=1)
        self._graph_period_value = QLabel()
        self._graph_period_value.setFixedWidth(80)
        self._graph_period_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        graph_period_row.addWidget(self._graph_period_value)
        self._graph_period_slider.valueChanged.connect(
            self._update_graph_period_value
        )
        layout.addLayout(graph_period_row)

        detector_row = QHBoxLayout()
        self._peak_detector_label = QLabel(t("sys_engineering_peak_detector"))
        detector_row.addWidget(self._peak_detector_label)
        self._peak_detector_combo = QComboBox()
        self._peak_detector_combo.addItem(
            t("sys_peak_detector_mad_mean"), "mad_mean"
        )
        self._peak_detector_combo.addItem(
            t("sys_peak_detector_derivative"), "derivative"
        )
        self._peak_detector_combo.addItem(t("sys_peak_detector_legacy"), "legacy")
        self._peak_detector_combo.setMinimumWidth(280)
        detector_row.addWidget(self._peak_detector_combo)
        detector_row.addStretch()
        layout.addLayout(detector_row)

        identification_row = QHBoxLayout()
        self._breathing_identification_label = QLabel(
            t("sys_engineering_breathing_identification")
        )
        identification_row.addWidget(self._breathing_identification_label)
        self._breathing_identification_combo = QComboBox()
        self._breathing_identification_combo.addItem(
            t("sys_breathing_identification_model"), "model"
        )
        self._breathing_identification_combo.addItem(
            t("sys_breathing_identification_spectral"), "spectral"
        )
        self._breathing_identification_combo.setMinimumWidth(280)
        identification_row.addWidget(self._breathing_identification_combo)
        identification_row.addStretch()
        layout.addLayout(identification_row)

        self._engineering_hint = QLabel(t("sys_engineering_hint"))
        self._engineering_hint.setWordWrap(True)
        self._engineering_hint.setStyleSheet(f"color:{C['text_dim']};")
        layout.addWidget(self._engineering_hint)
        layout.addStretch()

        self._build_trends_configuration_tab()
        self._build_peep_configuration_tab()
        self._build_visibility_tab()
        self._build_section_configuration_tab()
        self._build_appearance_configuration_tab()
        self._build_reference_tab()

        button_row = QHBoxLayout()
        button_row.addStretch()
        self._section_save = QPushButton(t("sys_section_save"))
        self._section_save.setFixedSize(220, 44)
        self._section_save.setEnabled(False)
        self._section_save.setStyleSheet(f"""
            QPushButton {{
                background:{C['bg_card']};color:{C['text']};
                border:1px solid {C['blue_light']};border-radius:6px;
                font-size:{FONT_BTN}px;font-weight:bold;padding:8px 20px;
            }}
            QPushButton:hover {{ background:{C['nav_hover']}; }}
            QPushButton:disabled {{ color:{C['text_dim']};border-color:{C['border']}; }}
        """)
        self._section_save.clicked.connect(
            self._section_profile_editor.save_profile
        )
        button_row.addWidget(self._section_save)
        self._engineering_apply = QPushButton(t("sys_engineering_apply"))
        self._engineering_apply.setFixedSize(220, 44)
        self._engineering_apply.setStyleSheet(f"""
            QPushButton {{
                background:{C['blue']};color:white;
                border:1px solid {C['blue_light']};border-radius:6px;
                font-size:{FONT_BTN}px;font-weight:bold;padding:8px 20px;
            }}
            QPushButton:hover {{ background:{C['blue_hover']}; }}
            QPushButton:pressed {{ background:{C['blue_dark']}; }}
            QPushButton:disabled {{
                background:{C['bg_card']};color:{C['text_dim']};
                border-color:{C['border']};
            }}
        """)
        self._engineering_apply.clicked.connect(self._save_engineering_settings)
        button_row.addWidget(self._engineering_apply)
        outer.addLayout(button_row)
        self._engineering_sections.currentChanged.connect(
            self._sync_engineering_action_visibility
        )
        self._sync_engineering_action_visibility(
            self._engineering_sections.currentIndex()
        )
        self._section_profile_editor.dirty_changed.connect(
            self._on_section_dirty_changed
        )

        current = (
            self._engineering_settings.current
            if self._engineering_settings is not None
            else EngineeringSettings()
        )
        self._load_engineering_settings(current)

    def _build_trends_configuration_tab(self) -> None:
        outer = QVBoxLayout(self._engineering_trends_tab)
        outer.setContentsMargins(0, 0, 0, 0)
        trend_scroll = QScrollArea()
        trend_scroll.setObjectName("engineering_trend_settings_scroll")
        trend_scroll.setWidgetResizable(True)
        trend_scroll.setFrameShape(QFrame.NoFrame)
        trend_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        trend_scroll.setStyleSheet(f"""
            QScrollBar:vertical {{
                background:{C['bg_panel']};width:22px;margin:0;
            }}
            QScrollBar::handle:vertical {{
                background:{C['border_light']};min-height:48px;border-radius:8px;
                margin:2px 4px;
            }}
            QScrollBar::handle:vertical:pressed {{ background:{C['blue_light']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background:transparent;
            }}
        """)
        outer.addWidget(trend_scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        trend_scroll.setWidget(content)

        chart_row = QHBoxLayout()
        self._trend_chart_mode_label = QLabel(
            t("sys_engineering_trend_chart_mode")
        )
        chart_row.addWidget(self._trend_chart_mode_label)
        self._trend_chart_mode_combo = QComboBox()
        self._trend_chart_mode_combo.addItem(t("sys_trend_chart_bars"), "bars")
        self._trend_chart_mode_combo.addItem(t("sys_trend_chart_lines"), "lines")
        self._trend_chart_mode_combo.setMinimumWidth(360)
        chart_row.addWidget(self._trend_chart_mode_combo)
        chart_row.addStretch()
        layout.addLayout(chart_row)

        rounding_row = QHBoxLayout()
        self._trend_rounding_label = QLabel(
            t("sys_engineering_trend_rounding")
        )
        rounding_row.addWidget(self._trend_rounding_label)
        self._trend_rounding_spin = QSpinBox()
        self._trend_rounding_spin.setRange(
            MIN_TREND_DECIMAL_PLACES, MAX_TREND_DECIMAL_PLACES
        )
        self._trend_rounding_spin.setSingleStep(1)
        self._trend_rounding_spin.setMinimumSize(140, 48)
        rounding_row.addWidget(self._trend_rounding_spin)
        rounding_row.addStretch()
        layout.addLayout(rounding_row)

        point_row = QHBoxLayout()
        self._trend_point_mode_label = QLabel(t("sys_engineering_trend_point_mode"))
        point_row.addWidget(self._trend_point_mode_label)
        self._trend_point_mode_combo = QComboBox()
        self._trend_point_mode_combo.addItem(
            t("sys_trend_points_interval"), "interval"
        )
        self._trend_point_mode_combo.addItem(
            t("sys_trend_points_breath_cycle"), "breath_cycle"
        )
        self._trend_point_mode_combo.setMinimumWidth(360)
        point_row.addWidget(self._trend_point_mode_combo)
        point_row.addStretch()
        layout.addLayout(point_row)

        downsampling_row = QHBoxLayout()
        self._trend_downsampling_label = QLabel(
            t("sys_engineering_trend_downsampling")
        )
        downsampling_row.addWidget(self._trend_downsampling_label)
        self._trend_downsampling_combo = QComboBox()
        self._trend_downsampling_combo.addItem(
            t("sys_trend_downsampling_none"), "none"
        )
        self._trend_downsampling_combo.addItem(
            t("sys_trend_downsampling_adult"), "manual_adult"
        )
        self._trend_downsampling_combo.addItem(
            t("sys_trend_downsampling_infant"), "manual_infant"
        )
        self._trend_downsampling_combo.setMinimumWidth(360)
        downsampling_row.addWidget(self._trend_downsampling_combo)
        downsampling_row.addStretch()
        layout.addLayout(downsampling_row)

        self._trend_configuration_hint = QLabel(
            t("sys_engineering_trend_configuration_hint")
        )
        self._trend_configuration_hint.setWordWrap(True)
        self._trend_configuration_hint.setStyleSheet(f"color:{C['text_dim']};")
        layout.addWidget(self._trend_configuration_hint)

        self._trend_visibility_title = QLabel(
            t("sys_engineering_trend_visibility")
        )
        self._trend_visibility_title.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_LABEL}px;font-weight:bold;"
        )
        layout.addWidget(self._trend_visibility_title)

        self._trend_visibility_hint = QLabel(
            t("sys_engineering_trend_visibility_hint")
        )
        self._trend_visibility_hint.setWordWrap(True)
        self._trend_visibility_hint.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;"
        )
        layout.addWidget(self._trend_visibility_hint)

        self._trend_visibility_group = QGroupBox()
        self._trend_visibility_group.setStyleSheet(f"""
            QGroupBox {{
                border:1px solid {C['blue_light']};border-radius:7px;
                margin-top:0;padding-top:10px;
            }}
        """)
        self._trend_visibility_grid = QGridLayout(self._trend_visibility_group)
        self._trend_visibility_grid.setContentsMargins(12, 14, 12, 14)
        self._trend_visibility_grid.setHorizontalSpacing(12)
        self._trend_visibility_grid.setVerticalSpacing(10)
        self._trend_visibility_checks: dict[str, QCheckBox] = {}
        self._hidden_trend_metrics_draft: set[str] = set()
        self._rebuild_trend_visibility_checks(self._roi_spin.value())
        self._roi_spin.valueChanged.connect(self._rebuild_trend_visibility_checks)
        layout.addWidget(self._trend_visibility_group)
        layout.addStretch()

    def _capture_trend_visibility_draft(self) -> None:
        for code, checkbox in self._trend_visibility_checks.items():
            if checkbox.isChecked():
                self._hidden_trend_metrics_draft.discard(code)
            else:
                self._hidden_trend_metrics_draft.add(code)

    def _rebuild_trend_visibility_checks(self, roi_count: int) -> None:
        self._capture_trend_visibility_draft()
        while self._trend_visibility_grid.count():
            item = self._trend_visibility_grid.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self._trend_visibility_checks = {}
        for index, (code, label) in enumerate(_trend_visibility_items(roi_count)):
            checkbox = QCheckBox(label)
            checkbox.setMinimumHeight(44)
            checkbox.setStyleSheet(_visibility_checkbox_style())
            checkbox.setChecked(code not in self._hidden_trend_metrics_draft)
            self._trend_visibility_grid.addWidget(checkbox, index // 3, index % 3)
            self._trend_visibility_checks[code] = checkbox

    def _selected_hidden_trend_metrics(self) -> tuple[str, ...]:
        self._capture_trend_visibility_draft()
        return tuple(
            code
            for code, _label in _trend_visibility_items(MAX_ROI_COUNT)
            if code in self._hidden_trend_metrics_draft
        )

    def _build_reference_tab(self) -> None:
        layout = QVBoxLayout(self._engineering_reference_tab)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("engineering_reference_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollBar:vertical {{
                background:{C['bg_panel']};width:22px;margin:0;
            }}
            QScrollBar::handle:vertical {{
                background:{C['border_light']};min-height:48px;border-radius:8px;
                margin:2px 4px;
            }}
            QScrollBar::handle:vertical:pressed {{ background:{C['blue_light']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background:transparent;
            }}
        """)
        layout.addWidget(scroll)

        content = QWidget()
        content.setObjectName("engineering_reference_content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 24)
        content_layout.setSpacing(10)

        self._reference_title = QLabel(t("sys_reference_title"))
        self._reference_title.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_TITLE}px;font-weight:bold;"
        )
        content_layout.addWidget(self._reference_title)

        self._reference_hint = QLabel(t("sys_reference_hint"))
        self._reference_hint.setWordWrap(True)
        self._reference_hint.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;"
        )
        content_layout.addWidget(self._reference_hint)

        self._reference_rows: list[tuple[str, str, str, QLabel, QLabel]] = []
        for code_key, static_code, description_key in _ENGINEERING_REFERENCE_ITEMS:
            row = QFrame()
            row.setObjectName("engineering_reference_row")
            row.setMinimumHeight(64)
            row.setStyleSheet(f"""
                QFrame#engineering_reference_row {{
                    background:{C['bg_card']};border:1px solid {C['border']};
                    border-radius:7px;
                }}
                QFrame#engineering_reference_row QLabel {{
                    background:transparent;border:none;
                }}
            """)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(16, 10, 16, 10)
            row_layout.setSpacing(18)

            code_label = QLabel(t(code_key) if code_key else static_code)
            code_label.setMinimumWidth(150)
            code_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            code_label.setStyleSheet(
                f"color:{C['blue_light']};font-size:{FONT_VALUE}px;font-weight:bold;"
            )
            description_label = QLabel(t(description_key))
            description_label.setWordWrap(True)
            description_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            description_label.setStyleSheet(
                f"color:{C['text']};font-size:{FONT_LABEL}px;"
            )
            row_layout.addWidget(code_label)
            row_layout.addWidget(description_label, stretch=1)
            content_layout.addWidget(row)
            self._reference_rows.append(
                (code_key, static_code, description_key, code_label, description_label)
            )

        content_layout.addStretch()
        scroll.setWidget(content)

    def _sync_engineering_action_visibility(self, index: int) -> None:
        reference_selected = (
            self._engineering_sections.widget(index)
            is self._engineering_reference_tab
        )
        self._section_save.setVisible(not reference_selected)
        self._engineering_apply.setVisible(not reference_selected)

    def _build_peep_configuration_tab(self) -> None:
        layout = QVBoxLayout(self._engineering_peep_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        self._peep_tab_visibility_check = QCheckBox(
            t("sys_engineering_peep_tab_visibility")
        )
        self._peep_tab_visibility_check.setStyleSheet(_visibility_checkbox_style())
        layout.addWidget(self._peep_tab_visibility_check)

        threshold_row = QHBoxLayout()
        self._peep_threshold_label = QLabel(t("sys_engineering_peep_threshold"))
        threshold_row.addWidget(self._peep_threshold_label)
        self._peep_threshold_spin = QSpinBox()
        self._peep_threshold_spin.setRange(
            MIN_PEEP_SILENT_THRESHOLD_PERCENT,
            MAX_PEEP_SILENT_THRESHOLD_PERCENT,
        )
        self._peep_threshold_spin.setSuffix(" % RTS")
        threshold_row.addWidget(self._peep_threshold_spin)
        threshold_row.addStretch()
        layout.addLayout(threshold_row)

        interval_row = QHBoxLayout()
        self._peep_interval_label = QLabel(t("sys_engineering_peep_interval"))
        interval_row.addWidget(self._peep_interval_label)
        self._peep_interval_spin = QSpinBox()
        self._peep_interval_spin.setRange(
            MIN_PEEP_ANALYSIS_INTERVAL_SECONDS,
            MAX_PEEP_ANALYSIS_INTERVAL_SECONDS,
        )
        self._peep_interval_spin.setSuffix(" " + t("analysis_seconds_short"))
        interval_row.addWidget(self._peep_interval_spin)
        interval_row.addStretch()
        layout.addLayout(interval_row)

        gravity_row = QHBoxLayout()
        self._peep_gravity_label = QLabel(t("sys_engineering_peep_gravity"))
        gravity_row.addWidget(self._peep_gravity_label)
        self._peep_gravity_spin = QSpinBox()
        self._peep_gravity_spin.setRange(-180, 180)
        self._peep_gravity_spin.setSuffix("°")
        gravity_row.addWidget(self._peep_gravity_spin)
        gravity_row.addStretch()
        layout.addLayout(gravity_row)

        self._peep_configuration_hint = QLabel(t("sys_engineering_peep_hint"))
        self._peep_configuration_hint.setWordWrap(True)
        self._peep_configuration_hint.setStyleSheet(f"color:{C['text_dim']};")
        layout.addWidget(self._peep_configuration_hint)
        layout.addStretch()

    def _build_visibility_tab(self) -> None:
        tab_layout = QVBoxLayout(self._engineering_visibility_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)
        tab_layout.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        self._navigation_visibility_group = QGroupBox(
            t("sys_engineering_navigation_visibility")
        )
        self._navigation_visibility_group.setStyleSheet(
            f"QGroupBox {{ border:1px solid {C['border']}; border-radius:8px; "
            f"margin-top:12px; padding-top:10px; font-weight:bold; }} "
            f"QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:0 6px; }}"
        )
        navigation_layout = QGridLayout(self._navigation_visibility_group)
        navigation_layout.setContentsMargins(14, 20, 14, 14)
        navigation_layout.setHorizontalSpacing(10)
        navigation_layout.setVerticalSpacing(10)
        self._tab_visibility_checks: dict[str, QCheckBox] = {}
        for index, tab in enumerate(INTERFACE_TABS):
            checkbox = QCheckBox(t(_INTERFACE_TAB_KEYS[tab]))
            checkbox.setStyleSheet(_visibility_checkbox_style())
            checkbox.setEnabled(tab not in REQUIRED_INTERFACE_TABS)
            navigation_layout.addWidget(checkbox, index // 5, index % 5)
            self._tab_visibility_checks[tab] = checkbox
        layout.addWidget(self._navigation_visibility_group)

        self._aeration_visibility_group = QGroupBox(
            t("sys_engineering_aeration_visibility")
        )
        self._aeration_visibility_group.setStyleSheet(
            f"QGroupBox {{ border:1px solid {C['blue_light']}; border-radius:8px; "
            f"margin-top:12px; padding-top:10px; font-weight:bold; }} "
            f"QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:0 6px; }}"
        )
        aeration_group_layout = QVBoxLayout(self._aeration_visibility_group)
        aeration_group_layout.setContentsMargins(14, 20, 14, 14)
        aeration_group_layout.setSpacing(10)
        self._aeration_visibility_hint = QLabel(
            t("sys_engineering_aeration_visibility_hint")
        )
        self._aeration_visibility_hint.setWordWrap(True)
        self._aeration_visibility_hint.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;"
        )
        aeration_group_layout.addWidget(self._aeration_visibility_hint)
        self._aeration_visibility_grid = QGridLayout()
        self._aeration_visibility_grid.setHorizontalSpacing(10)
        self._aeration_visibility_grid.setVerticalSpacing(10)
        aeration_group_layout.addLayout(self._aeration_visibility_grid)
        self._aeration_visibility_checks: dict[str, QCheckBox] = {}
        self._hidden_aeration_metrics_draft: set[str] = set()
        self._rebuild_aeration_visibility_checks(self._roi_spin.value())
        self._roi_spin.valueChanged.connect(
            self._rebuild_aeration_visibility_checks
        )
        layout.addWidget(self._aeration_visibility_group)

        self._element_visibility_group = QGroupBox(
            t("sys_engineering_element_visibility")
        )
        self._element_visibility_group.setStyleSheet(
            f"QGroupBox {{ border:1px solid {C['border']}; border-radius:8px; "
            f"margin-top:12px; padding-top:10px; font-weight:bold; }} "
            f"QGroupBox::title {{ subcontrol-origin:margin; left:14px; padding:0 6px; }}"
        )
        element_group_layout = QVBoxLayout(self._element_visibility_group)
        element_group_layout.setContentsMargins(14, 20, 14, 14)
        element_group_layout.setSpacing(12)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(12)
        self._element_visibility_label = QLabel(t("sys_engineering_configured_tab"))
        self._element_visibility_label.setStyleSheet(
            f"color:{C['text_dim']};font-size:{FONT_SMALL}px;font-weight:500;"
        )
        self._element_visibility_label.setFixedWidth(220)
        self._element_visibility_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        selector_row.addWidget(self._element_visibility_label)
        self._element_visibility_selector = QComboBox()
        self._element_visibility_selector.setStyleSheet(_visibility_combo_style())
        self._element_visibility_selector.setFixedHeight(48)
        self._element_visibility_selector.setMaximumWidth(520)
        self._element_visibility_selector.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self._element_visibility_selector.setMinimumContentsLength(24)
        selector_row.addWidget(self._element_visibility_selector)
        selector_row.addStretch()
        element_group_layout.addLayout(selector_row)

        self._element_visibility_stack = QStackedWidget()
        self._element_visibility_stack.setStyleSheet(
            f"QStackedWidget {{ background:{C['bg_panel']}; border:1px solid "
            f"{C['border']}; border-radius:6px; }}"
        )
        self._element_visibility_checks: dict[str, QCheckBox] = {}
        self._element_visibility_pages: dict[str, QWidget] = {}
        for tab in INTERFACE_TABS:
            page = QWidget()
            page.setStyleSheet("background: transparent;")
            page_layout = QGridLayout(page)
            page_layout.setContentsMargins(12, 12, 12, 12)
            page_layout.setHorizontalSpacing(10)
            page_layout.setVerticalSpacing(10)
            for index, element in enumerate(INTERFACE_ELEMENTS[tab]):
                checkbox = QCheckBox(t(_ELEMENT_LABEL_KEYS[element]))
                checkbox.setStyleSheet(_visibility_checkbox_style())
                page_layout.addWidget(checkbox, index // 2, index % 2)
                self._element_visibility_checks[element] = checkbox
            page_layout.setRowStretch((len(INTERFACE_ELEMENTS[tab]) + 1) // 2, 1)
            self._element_visibility_selector.addItem(_single_line_tab_text(tab), tab)
            self._element_visibility_stack.addWidget(page)
            self._element_visibility_pages[tab] = page
        self._element_visibility_selector.currentIndexChanged.connect(
            self._element_visibility_stack.setCurrentIndex
        )
        # Kept as a compatibility alias for code that only queries page count.
        self._element_visibility_tabs = self._element_visibility_stack
        element_group_layout.addWidget(self._element_visibility_stack, stretch=1)
        layout.addWidget(self._element_visibility_group, stretch=1)

        # Backward-compatible aliases used by older integrations and tests.
        self._show_main_trends_check = self._element_visibility_checks["main.trends"]
        self._show_main_tvi_check = self._element_visibility_checks["main.tvi"]
        self._peep_tab_visibility_check.toggled.connect(
            self._tab_visibility_checks["peep"].setChecked
        )
        self._tab_visibility_checks["peep"].toggled.connect(
            self._peep_tab_visibility_check.setChecked
        )

    def _capture_aeration_visibility_draft(self) -> None:
        for code, checkbox in self._aeration_visibility_checks.items():
            if checkbox.isChecked():
                self._hidden_aeration_metrics_draft.discard(code)
            else:
                self._hidden_aeration_metrics_draft.add(code)

    def _rebuild_aeration_visibility_checks(self, roi_count: int) -> None:
        self._capture_aeration_visibility_draft()
        while self._aeration_visibility_grid.count():
            item = self._aeration_visibility_grid.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self._aeration_visibility_checks = {}
        for index, (code, label) in enumerate(
            _aeration_visibility_items(roi_count)
        ):
            checkbox = QCheckBox(label)
            checkbox.setMinimumHeight(44)
            checkbox.setStyleSheet(_visibility_checkbox_style())
            checkbox.setChecked(code not in self._hidden_aeration_metrics_draft)
            self._aeration_visibility_grid.addWidget(
                checkbox, index // 3, index % 3
            )
            self._aeration_visibility_checks[code] = checkbox

    def _selected_hidden_aeration_metrics(self) -> tuple[str, ...]:
        self._capture_aeration_visibility_draft()
        return tuple(
            code
            for code, _label in _aeration_visibility_items(MAX_ROI_COUNT)
            if code in self._hidden_aeration_metrics_draft
        )

    def _build_section_configuration_tab(self) -> None:
        layout = QVBoxLayout(self._engineering_section_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        self._section_profile_editor = SectionProfileEditor()
        layout.addWidget(self._section_profile_editor)

    def _build_appearance_configuration_tab(self) -> None:
        layout = QVBoxLayout(self._engineering_appearance_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        background_row = QHBoxLayout()
        self._background_color_label = QLabel(
            t("sys_engineering_background_color")
        )
        background_row.addWidget(self._background_color_label)
        self._background_color_button = QPushButton()
        self._background_color_button.setMinimumSize(220, 48)
        self._background_color_button.clicked.connect(
            self._choose_background_color
        )
        background_row.addWidget(self._background_color_button)
        self._background_color_reset = QPushButton(
            t("sys_engineering_background_reset")
        )
        self._background_color_reset.setMinimumSize(220, 48)
        self._background_color_reset.clicked.connect(
            lambda: self._set_background_color(
                DEFAULT_APPLICATION_BACKGROUND_COLOR
            )
        )
        background_row.addWidget(self._background_color_reset)
        background_row.addStretch()
        layout.addLayout(background_row)
        self._waveform_fill_check = QCheckBox(t("sys_engineering_waveform_fill"))
        self._waveform_fill_check.setStyleSheet(
            _visibility_checkbox_style() + "QCheckBox { min-height: 30px; }"
        )
        layout.addWidget(self._waveform_fill_check)
        layout.addStretch()

    def _load_engineering_settings(self, settings: EngineeringSettings) -> None:
        for mode, checkbox in self._mode_checks.items():
            checkbox.setChecked(mode in settings.work_modes)
        self._roi_spin.setValue(settings.roi_count)
        self._graph_period_slider.setValue(settings.graph_display_period_seconds)
        self._set_background_color(settings.application_background_color)
        self._waveform_fill_check.setChecked(settings.waveform_fill_enabled)
        detector_index = self._peak_detector_combo.findData(
            settings.peak_detection_method
        )
        self._peak_detector_combo.setCurrentIndex(max(0, detector_index))
        identification_index = self._breathing_identification_combo.findData(
            settings.breathing_identification_method
        )
        self._breathing_identification_combo.setCurrentIndex(
            max(0, identification_index)
        )
        point_mode_index = self._trend_point_mode_combo.findData(
            settings.trend_point_mode
        )
        self._trend_point_mode_combo.setCurrentIndex(max(0, point_mode_index))
        chart_mode_index = self._trend_chart_mode_combo.findData(
            settings.trend_chart_mode
        )
        self._trend_chart_mode_combo.setCurrentIndex(max(0, chart_mode_index))
        self._trend_rounding_spin.setValue(settings.trend_decimal_places)
        self._hidden_trend_metrics_draft = set(settings.hidden_trend_metrics)
        self._rebuild_trend_visibility_checks(settings.roi_count)
        self._hidden_aeration_metrics_draft = set(
            settings.hidden_aeration_metrics
        )
        self._rebuild_aeration_visibility_checks(settings.roi_count)
        downsampling_index = self._trend_downsampling_combo.findData(
            settings.trend_downsampling_mode
        )
        self._trend_downsampling_combo.setCurrentIndex(
            max(0, downsampling_index)
        )
        self._peep_threshold_spin.setValue(settings.peep_silent_threshold_percent)
        self._peep_interval_spin.setValue(settings.peep_analysis_interval_seconds)
        self._peep_gravity_spin.setValue(settings.peep_gravity_angle_degrees)
        for tab, checkbox in self._tab_visibility_checks.items():
            checkbox.setChecked(tab in settings.visible_tabs)
        for element, checkbox in self._element_visibility_checks.items():
            checkbox.setChecked(settings.is_element_visible(element))
        self._peep_tab_visibility_check.setChecked(
            "peep" in settings.visible_tabs
        )
        self._section_profile_editor.load(
            settings.section_profile, settings.custom_section_profiles
        )

    def _validate_mode_selection(self, mode: str, checked: bool) -> None:
        if not checked and not any(box.isChecked() for box in self._mode_checks.values()):
            self._mode_checks[mode].setChecked(True)

    def _save_engineering_settings(self) -> None:
        if self._section_profile_editor.has_unsaved_changes:
            return
        settings = EngineeringSettings(
            work_modes=tuple(
                mode for mode, checkbox in self._mode_checks.items() if checkbox.isChecked()
            ),
            roi_count=self._roi_spin.value(),
            peak_detection_method=str(self._peak_detector_combo.currentData()),
            breathing_identification_method=str(
                self._breathing_identification_combo.currentData()
            ),
            application_background_color=self._selected_background_color,
            waveform_fill_enabled=self._waveform_fill_check.isChecked(),
            graph_display_period_seconds=self._graph_period_slider.value(),
            trend_point_mode=str(self._trend_point_mode_combo.currentData()),
            trend_downsampling_mode=str(
                self._trend_downsampling_combo.currentData()
            ),
            trend_chart_mode=str(self._trend_chart_mode_combo.currentData()),
            trend_decimal_places=self._trend_rounding_spin.value(),
            hidden_trend_metrics=self._selected_hidden_trend_metrics(),
            hidden_aeration_metrics=self._selected_hidden_aeration_metrics(),
            peep_silent_threshold_percent=self._peep_threshold_spin.value(),
            peep_analysis_interval_seconds=self._peep_interval_spin.value(),
            peep_gravity_angle_degrees=self._peep_gravity_spin.value(),
            visible_tabs=tuple(
                tab
                for tab in INTERFACE_TABS
                if self._tab_visibility_checks[tab].isChecked()
            ),
            show_main_trends=self._show_main_trends_check.isChecked(),
            show_main_tvi=self._show_main_tvi_check.isChecked(),
            visible_elements=tuple(
                element
                for tab in INTERFACE_TABS
                for element in INTERFACE_ELEMENTS[tab]
                if self._element_visibility_checks[element].isChecked()
            ),
            section_profile=self._section_profile_editor.active_profile,
            custom_section_profiles=self._section_profile_editor.custom_profiles,
        )
        if self._engineering_settings is not None:
            self._engineering_settings.save(settings)
        self._section_profile_editor.load(
            settings.section_profile, settings.custom_section_profiles
        )
        self._engineering_apply.setText(t("sys_engineering_saved"))
        QTimer.singleShot(
            1500,
            lambda: self._engineering_apply.setText(t("sys_engineering_apply")),
        )

    def _on_section_dirty_changed(self, dirty: bool) -> None:
        self._section_save.setEnabled(
            dirty and self._section_profile_editor.can_save
        )
        self._engineering_apply.setEnabled(not dirty)
        self._engineering_apply.setToolTip(
            t("sys_section_apply_blocked_tooltip") if dirty else ""
        )

    def _update_graph_period_value(self, seconds: int | None = None) -> None:
        value = self._graph_period_slider.value() if seconds is None else seconds
        self._graph_period_value.setText(
            t("sys_engineering_graph_period_value").format(seconds=value)
        )

    def _choose_background_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(self._selected_background_color),
            self,
            t("sys_engineering_background_picker_title"),
        )
        if selected.isValid():
            self._set_background_color(selected.name())

    def _set_background_color(self, color: str) -> None:
        normalized = QColor(color).name()
        if not QColor(color).isValid():
            normalized = DEFAULT_APPLICATION_BACKGROUND_COLOR
        self._selected_background_color = normalized
        swatch = QColor(normalized)
        text_color = "#101820" if swatch.lightness() >= 140 else "#ffffff"
        self._background_color_button.setText(normalized.upper())
        self._background_color_button.setStyleSheet(
            f"background-color:{normalized};color:{text_color};"
            f"border:2px solid {C['border_light']};border-radius:6px;"
            f"font-size:{FONT_BTN}px;font-weight:bold;min-height:44px;"
        )
        self._background_color_reset.setEnabled(
            normalized != DEFAULT_APPLICATION_BACKGROUND_COLOR
        )

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
            if lbl_key == "sys_lbl_device_model":
                val_key = self._device_mode_text()
                val_is_i18n = False
            value = t(val_key) if val_is_i18n else val_key
            i18n_key = val_key if val_is_i18n else ""
            lbl = self._dcell(value, bold=True)
            if lbl_key == "sys_lbl_device_model":
                self._device_model_lbl = lbl
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
        self._tabs.setTabText(0, t("sys_tab_information"))
        self._tabs.setTabText(1, t("sys_tab_engineering"))
        self._engineering_sections.setTabText(0, t("sys_engineering_tab_general"))
        self._engineering_sections.setTabText(1, t("sys_engineering_tab_trends"))
        self._engineering_sections.setTabText(2, t("sys_engineering_tab_peep"))
        self._engineering_sections.setTabText(3, t("sys_engineering_tab_visibility"))
        self._engineering_sections.setTabText(4, t("sys_engineering_tab_section"))
        self._engineering_sections.setTabText(
            5, t("sys_engineering_tab_appearance")
        )
        self._engineering_sections.setTabText(
            6, t("sys_engineering_tab_reference")
        )
        self._reference_title.setText(t("sys_reference_title"))
        self._reference_hint.setText(t("sys_reference_hint"))
        for (
            code_key, static_code, description_key, code_label, description_label,
        ) in self._reference_rows:
            code_label.setText(t(code_key) if code_key else static_code)
            description_label.setText(t(description_key))
        self._section_profile_editor.retranslate()
        self._mode_group.setTitle(t("sys_engineering_modes"))
        for mode, key in (
            ("adult", "sys_mode_adult"),
            ("infant", "sys_mode_infant"),
            ("ventilation", "sys_mode_ventilation"),
        ):
            self._mode_checks[mode].setText(t(key))
        self._roi_label.setText(t("sys_engineering_roi_count"))
        self._graph_period_label.setText(t("sys_engineering_graph_period"))
        self._background_color_label.setText(
            t("sys_engineering_background_color")
        )
        self._background_color_reset.setText(
            t("sys_engineering_background_reset")
        )
        self._waveform_fill_check.setText(t("sys_engineering_waveform_fill"))
        self._update_graph_period_value()
        self._peak_detector_label.setText(t("sys_engineering_peak_detector"))
        self._peak_detector_combo.setItemText(
            0, t("sys_peak_detector_mad_mean")
        )
        self._peak_detector_combo.setItemText(1, t("sys_peak_detector_derivative"))
        self._peak_detector_combo.setItemText(2, t("sys_peak_detector_legacy"))
        self._breathing_identification_label.setText(
            t("sys_engineering_breathing_identification")
        )
        self._breathing_identification_combo.setItemText(
            0, t("sys_breathing_identification_model")
        )
        self._breathing_identification_combo.setItemText(
            1, t("sys_breathing_identification_spectral")
        )
        self._trend_point_mode_label.setText(t("sys_engineering_trend_point_mode"))
        self._trend_chart_mode_label.setText(
            t("sys_engineering_trend_chart_mode")
        )
        self._trend_chart_mode_combo.setItemText(0, t("sys_trend_chart_bars"))
        self._trend_chart_mode_combo.setItemText(1, t("sys_trend_chart_lines"))
        self._trend_rounding_label.setText(t("sys_engineering_trend_rounding"))
        self._trend_visibility_title.setText(
            t("sys_engineering_trend_visibility")
        )
        self._trend_visibility_hint.setText(
            t("sys_engineering_trend_visibility_hint")
        )
        self._aeration_visibility_group.setTitle(
            t("sys_engineering_aeration_visibility")
        )
        self._aeration_visibility_hint.setText(
            t("sys_engineering_aeration_visibility_hint")
        )
        self._trend_point_mode_combo.setItemText(0, t("sys_trend_points_interval"))
        self._trend_point_mode_combo.setItemText(
            1, t("sys_trend_points_breath_cycle")
        )
        self._trend_downsampling_label.setText(
            t("sys_engineering_trend_downsampling")
        )
        self._trend_downsampling_combo.setItemText(
            0, t("sys_trend_downsampling_none")
        )
        self._trend_downsampling_combo.setItemText(
            1, t("sys_trend_downsampling_adult")
        )
        self._trend_downsampling_combo.setItemText(
            2, t("sys_trend_downsampling_infant")
        )
        self._trend_configuration_hint.setText(
            t("sys_engineering_trend_configuration_hint")
        )
        self._peep_threshold_label.setText(t("sys_engineering_peep_threshold"))
        self._peep_tab_visibility_check.setText(
            t("sys_engineering_peep_tab_visibility")
        )
        self._peep_interval_label.setText(t("sys_engineering_peep_interval"))
        self._peep_interval_spin.setSuffix(" " + t("analysis_seconds_short"))
        self._peep_gravity_label.setText(t("sys_engineering_peep_gravity"))
        self._peep_configuration_hint.setText(t("sys_engineering_peep_hint"))
        self._engineering_hint.setText(t("sys_engineering_hint"))
        self._navigation_visibility_group.setTitle(
            t("sys_engineering_navigation_visibility")
        )
        for tab, checkbox in self._tab_visibility_checks.items():
            checkbox.setText(t(_INTERFACE_TAB_KEYS[tab]))
        self._element_visibility_group.setTitle(
            t("sys_engineering_element_visibility")
        )
        self._element_visibility_label.setText(t("sys_engineering_configured_tab"))
        for index, tab in enumerate(INTERFACE_TABS):
            self._element_visibility_selector.setItemText(
                index, _single_line_tab_text(tab)
            )
        for element, checkbox in self._element_visibility_checks.items():
            checkbox.setText(t(_ELEMENT_LABEL_KEYS[element]))
        self._engineering_apply.setText(t("sys_engineering_apply"))
        self._section_save.setText(t("sys_section_save"))
        if self._section_profile_editor.has_unsaved_changes:
            self._engineering_apply.setToolTip(
                t("sys_section_apply_blocked_tooltip")
            )

        for lbl_key, lbl in self._param_lbls:
            lbl.setText(t(lbl_key))

        for i18n_key, lbl in self._val_lbls:
            if i18n_key:
                lbl.setText(t(i18n_key))

        if self._lang_val_lbl is not None:
            self._lang_val_lbl.setText(LANGUAGES.get(i18n.lang, i18n.lang))

        if self._btn_change is not None:
            self._btn_change.setText(t("sys_lang_change_btn"))
        if self._device_model_lbl is not None:
            self._device_model_lbl.setText(self._device_mode_text())

    def _device_mode_text(self) -> str:
        if self._config.data_mode is DataMode.SIMULATION:
            return t("sys_mode_simulation")
        if self._config.data_mode is DataMode.FROMFILE:
            return f"{t('sys_mode_fromfile')} ({self._config.fromfile_path.name})"
        endpoint = self._config.device_endpoint or t("sys_not_configured")
        return f"{t('sys_mode_device')} ({endpoint})"

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
