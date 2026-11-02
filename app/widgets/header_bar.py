"""Top status bar — always visible across all screens.

Supports runtime language switching via i18n.language_changed.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QDateTime
from ..styles import C, FONT_HEADER, FONT_SMALL, FONT_VALUE
from ..i18n import t, i18n

_HDR_STATUS_MIN_H = 36


def _sep(parent=None):
    f = QFrame(parent)
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"color: {C['border']}; min-width: 1px; max-width: 1px;")
    return f


class HeaderBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {C['bg_header']};
                border-bottom: 2px solid {C['border']};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        # ── Hamburger menu ───────────────────────────────────────────────────
        self.btn_menu = QPushButton("≡")
        self.btn_menu.setFixedSize(36, 36)
        self.btn_menu.setStyleSheet(self._icon_btn_style())
        layout.addWidget(self.btn_menu)

        layout.addWidget(_sep())

        self._patient_mode = "child"

        # ── Mode indicator ───────────────────────────────────────────────────
        self.lbl_mode = QLabel(t("hdr_live"))
        self._playback_mode = False
        self.lbl_mode.setFixedSize(62, 34)
        self.lbl_mode.setAlignment(Qt.AlignCenter)
        self._set_mode_style(False)
        layout.addWidget(self.lbl_mode)

        layout.addWidget(_sep())

        # ── Breathing type display ───────────────────────────────────────────
        self.lbl_breath_type = QLabel(f"  {t('analysis_bt_undetermined')}  ")
        self.lbl_breath_type.setAlignment(Qt.AlignCenter)
        self.lbl_breath_type.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_breath_type.setStyleSheet(self._breath_style(False))
        layout.addWidget(self.lbl_breath_type, stretch=1)

        layout.addWidget(_sep())

        # ── Alarm button ─────────────────────────────────────────────────────
        self.btn_alarm = QPushButton(t("hdr_alarm"))
        self.btn_alarm.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.btn_alarm.setStyleSheet(self._alarm_style(False))
        self._alarm_active = False
        layout.addWidget(self.btn_alarm)

        layout.addWidget(_sep())

        # ── Battery ──────────────────────────────────────────────────────────
        batt_col = QWidget()
        batt_col.setFixedWidth(90)
        batt_layout = QHBoxLayout(batt_col)
        batt_layout.setContentsMargins(0, 0, 0, 0)
        batt_layout.setSpacing(4)
        batt_icon = QLabel("🔋")
        batt_icon.setStyleSheet("background: transparent; font-size: 18px;")
        self.lbl_battery = QLabel("95 %")
        self.lbl_battery.setStyleSheet(
            f"color: {C['ok_hover']}; font-size: {FONT_HEADER}px; font-weight: bold; background: transparent;"
        )
        batt_layout.addWidget(batt_icon)
        batt_layout.addWidget(self.lbl_battery)
        layout.addWidget(batt_col)

        layout.addWidget(_sep())

        # ── Time ─────────────────────────────────────────────────────────────
        self.lbl_time = QLabel("00:00")
        self.lbl_time.setFixedWidth(70)
        self.lbl_time.setAlignment(Qt.AlignCenter)
        self.lbl_time.setStyleSheet(
            f"color: {C['text']}; font-size: {FONT_VALUE}px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(self.lbl_time)

        # ── Clock timer ──────────────────────────────────────────────────────
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)
        self._tick_clock()

        i18n.language_changed.connect(self.retranslate)

    # ── Public ───────────────────────────────────────────────────────────────

    def retranslate(self):
        self.btn_menu.setToolTip(t("hdr_menu_tooltip"))
        self.btn_alarm.setText(t("hdr_alarm"))
        if not self._alarm_active:
            self.lbl_breath_type.setText(f"  {t('analysis_bt_undetermined')}  ")
        self.lbl_mode.setText(
            t("hdr_playback") if self._playback_mode else t("hdr_live")
        )

    def set_playback_mode(self, active: bool) -> None:
        self._playback_mode = active
        self.lbl_mode.setText(t("hdr_playback") if active else t("hdr_live"))
        self._set_mode_style(active)

    def _set_mode_style(self, playback: bool) -> None:
        color = C['warn'] if playback else "#40c4ff"
        background = "#3a2200" if playback else "#0d3a7a"
        self.lbl_mode.setStyleSheet(f"""
            background-color: {background};
            color: {color};
            border: 1px solid {C['border_light']};
            border-radius: 4px;
            font-size: {FONT_SMALL}px;
            font-weight: bold;
        """)

    def set_alarm(self, active: bool, text: str = ""):
        self._alarm_active = active
        self.btn_alarm.setStyleSheet(self._alarm_style(active))
        if active:
            self.btn_alarm.setText(f"⚠  {text or t('hdr_alarm')}")
        else:
            self.btn_alarm.setText(t("hdr_alarm"))

    def set_breath_type(self, text: str, is_pathological: bool = False):
        self.lbl_breath_type.setStyleSheet(self._breath_style(is_pathological))
        self.lbl_breath_type.setText(f"  {text}  ")

    # ── Private ───────────────────────────────────────────────────────────────

    def _tick_clock(self):
        self.lbl_time.setText(QDateTime.currentDateTime().toString("HH:mm"))

    def _breath_style(self, is_pathological: bool) -> str:
        if is_pathological:
            return f"""
                background-color: #2a1400;
                color: {C['warn']};
                border: 1px solid #7a3a00;
                border-radius: 4px;
                font-size: {FONT_HEADER}px; font-weight: 600;
                padding: 0 12px; min-height: {_HDR_STATUS_MIN_H}px;
            """
        return f"""
            background-color: #0a1e0a;
            color: #69f0ae;
            border: 1px solid #1b5e20;
            border-radius: 4px;
            font-size: {FONT_HEADER}px; font-weight: 600;
            padding: 0 12px; min-height: {_HDR_STATUS_MIN_H}px;
        """

    def _alarm_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background-color: {C['alarm']};
                    color: white;
                    border: 1px solid #b71c1c;
                    border-radius: 4px;
                    font-size: {FONT_HEADER}px; font-weight: bold;
                    padding: 0 12px;
                    min-height: {_HDR_STATUS_MIN_H}px;
                }}
            """
        return f"""
            QPushButton {{
                background-color: #1a0a0a;
                color: #555;
                border: 1px solid #3a1a1a;
                border-radius: 4px;
                font-size: {FONT_HEADER}px; font-weight: bold;
                padding: 0 12px;
                min-height: {_HDR_STATUS_MIN_H}px;
            }}
        """

    def _icon_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background-color: {C['bg_nav']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 4px;
                font-size: 20px;
            }}
            QPushButton:hover {{ background-color: {C['blue_hover']}; }}
        """

