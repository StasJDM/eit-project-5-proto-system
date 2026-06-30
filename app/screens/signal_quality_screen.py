"""Качество сигнала ЭС — electrode signal quality check screen.

Shows a torso cross-section with 16 electrodes coloured by signal level,
a bar chart below, and a legend with 5 quality categories.
"""

import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
)

from ..styles import C, FONT_BASE, FONT_LABEL, FONT_SMALL, FONT_BTN
from ..i18n import t, i18n
from ..session_timers import SessionTimers
from ..widgets.duration_counters import DurationCounterBar

# ── Mock signal levels (0.0 – 1.0) for electrodes 1-16 ──────────────────────
_SIGNAL: list[float] = [
    0.90, 0.88, 0.92, 0.85,        # 1-4   Сильный
    0.42,                           # 5     Слабый
    0.78, 0.82, 0.87,              # 6-8   Сильный
    0.22,                           # 9     Недостаточно
    0.85, 0.91, 0.88, 0.86, 0.89, # 10-14 Сильный
    0.19,                           # 15    Недостаточно
    0.80,                           # 16    Сильный
]

# Quality thresholds: (min_value, fill_color, i18n_key)
_QUALITY: list[tuple[float, str, str]] = [
    (0.70, "#2e7d32", "sq_quality_strong"),
    (0.50, "#0097a7", "sq_quality_adequate"),
    (0.30, "#f9a825", "sq_quality_weak"),
    (0.01, "#c62828", "sq_quality_insufficient"),
    (0.00, "#263238", "sq_quality_tech_error"),
]

_LEGEND_BOX = 24
_LEGEND_FONT = FONT_BASE
_LEGEND_COLORS = [c for _, c, _ in reversed(_QUALITY)]   # dark → green order in legend
_LEGEND_KEYS   = [k for _, _, k in reversed(_QUALITY)]


def _sig_color(v: float) -> str:
    for threshold, color, _ in _QUALITY:
        if v >= threshold:
            return color
    return _QUALITY[-1][1]


# ── Electrode placement diagram ───────────────────────────────────────────────

class _ElectrodeDiagram(QWidget):
    """Torso cross-section with 16 electrodes positioned around the perimeter."""

    def __init__(self, signals: list[float], parent=None):
        super().__init__(parent)
        self._signals = signals
        self.setMinimumSize(240, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:transparent;")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2

        # Use the smallest dimension to keep proportions
        scale = min(w, h)
        er = max(10, int(scale * 0.038))      # electrode circle radius
        torso_rx = int(scale * 0.30)
        torso_ry = int(scale * 0.34)
        elec_rx = torso_rx + er + 5
        elec_ry = torso_ry + er + 5

        # ── Torso outline ──────────────────────────────────────────────────
        p.setPen(QPen(QColor(C['border_light']), 2))
        p.setBrush(QBrush(QColor(C['thorax'])))
        p.drawEllipse(cx - torso_rx, cy - torso_ry, 2 * torso_rx, 2 * torso_ry)

        # ── Lung ellipses ──────────────────────────────────────────────────
        l_rx = int(torso_rx * 0.30)
        l_ry = int(torso_ry * 0.48)
        l_off = int(torso_ry * 0.04)
        left_cx  = cx - int(torso_rx * 0.34)
        right_cx = cx + int(torso_rx * 0.34)

        for lcx, col_key in [(left_cx, "lung_left"), (right_cx, "lung_right")]:
            col = C[col_key]
            p.setPen(QPen(QColor(col), 1))
            p.setBrush(QBrush(QColor(col + "44")))
            p.drawEllipse(lcx - l_rx, cy - l_ry + l_off, 2 * l_rx, 2 * l_ry)

        # ── L / R labels ───────────────────────────────────────────────────
        f_lr = QFont("Segoe UI", max(9, er - 2), QFont.Bold)
        p.setFont(f_lr)
        p.setPen(QColor(C['text']))
        fm = QFontMetrics(f_lr)
        for text, tx in [("L", left_cx), ("R", right_cx)]:
            p.drawText(tx - fm.horizontalAdvance(text) // 2,
                       cy + fm.ascent() // 2, text)

        # ── V / D labels ───────────────────────────────────────────────────
        f_vd = QFont("Segoe UI", FONT_SMALL)
        p.setFont(f_vd)
        p.setPen(QColor(C['text_dim']))
        fm2 = QFontMetrics(f_vd)
        p.drawText(cx - fm2.horizontalAdvance("V") // 2,
                   cy - elec_ry - er - 4, "V")
        p.drawText(cx - fm2.horizontalAdvance("D") // 2,
                   cy + elec_ry + er + fm2.ascent() + 2, "D")

        # ── Electrodes ─────────────────────────────────────────────────────
        f_e = QFont("Segoe UI", max(6, er - 4), QFont.Bold)
        p.setFont(f_e)
        fm_e = QFontMetrics(f_e)

        for i, sig in enumerate(self._signals):
            angle_rad = math.radians(-90 + i * (360 / 16))
            ex = int(cx + elec_rx * math.cos(angle_rad))
            ey = int(cy + elec_ry * math.sin(angle_rad))

            col = QColor(_sig_color(sig))
            p.setPen(QPen(col.darker(170), 1))
            p.setBrush(QBrush(col))
            p.drawEllipse(ex - er, ey - er, 2 * er, 2 * er)

            label = str(i + 1)
            tw = fm_e.horizontalAdvance(label)
            p.setPen(QColor("white"))
            p.drawText(ex - tw // 2, ey + fm_e.ascent() // 2, label)


# ── Bar chart ─────────────────────────────────────────────────────────────────

class _BarChart(QWidget):
    """Bar chart of signal quality per electrode with a threshold line."""

    _THRESHOLD = 0.50

    def __init__(self, signals: list[float], parent=None):
        super().__init__(parent)
        self._signals = signals
        self.setMinimumHeight(120)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(
            f"background-color:{C['bg_wave']};"
            f"border:1px solid {C['border']};border-radius:4px;"
        )

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        ml, mr, mt, mb = 6, 6, 6, 22

        chart_w = w - ml - mr
        chart_h = h - mt - mb
        n = len(self._signals)
        gap = 3
        bar_w = max(4, (chart_w - gap * (n - 1)) // n)

        # Bars
        for i, sig in enumerate(self._signals):
            bx = ml + i * (bar_w + gap)
            bh = max(1, int((1.0 - sig) * chart_h))
            by = mt + chart_h - bh
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(_sig_color(sig))))
            p.drawRect(bx, by, bar_w, bh)

        # Threshold dashed line
        ty = mt + int(chart_h * (1 - self._THRESHOLD))
        p.setPen(QPen(QColor(C['text_dim']), 1, Qt.DashLine))
        p.drawLine(ml, ty, w - mr, ty)

        # Baseline
        p.setPen(QPen(QColor(C['border_light']), 1))
        p.drawLine(ml, mt + chart_h, w - mr, mt + chart_h)

        # X-axis labels (every electrode number)
        f_ax = QFont("Segoe UI", FONT_SMALL)
        p.setFont(f_ax)
        fm = QFontMetrics(f_ax)
        p.setPen(QColor(C['text_dim']))
        for i in range(n):
            bx = ml + i * (bar_w + gap)
            label = str(i + 1)
            tw = fm.horizontalAdvance(label)
            p.drawText(bx + (bar_w - tw) // 2, h - 5, label)


# ── Signal quality screen ─────────────────────────────────────────────────────

class SignalQualityScreen(QWidget):
    """Качество сигнала ЭС — EIT electrode signal quality check screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color:{C['bg_main']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(8)

        # ── Duration row ──────────────────────────────────────────────────────
        self._dur_bar = DurationCounterBar()
        outer.addWidget(self._dur_bar)

        timers = SessionTimers.instance(self)
        timers.updated.connect(self._dur_bar.set_values)
        self._dur_bar.set_values(*timers.values())

        # ── Electrode diagram (centred) ────────────────────────────────────────
        diag_row = QHBoxLayout()
        self._diagram = _ElectrodeDiagram(_SIGNAL)
        diag_row.addStretch()
        diag_row.addWidget(self._diagram)
        diag_row.addStretch()
        outer.addLayout(diag_row, stretch=3)

        # ── Bar chart + Calibrate button ──────────────────────────────────────
        chart_row = QHBoxLayout()
        chart_row.setSpacing(10)

        self._btn_calibrate = QPushButton(t("sq_btn_calibrate"))
        self._btn_calibrate.setMinimumWidth(118)
        self._btn_calibrate.setFixedHeight(56)
        self._btn_calibrate.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['warn']}22;
                color: {C['warn']};
                border: 1px solid {C['warn']};
                border-radius: 4px;
                font-size: {FONT_SMALL}px;
                font-weight: bold;
                padding: 4px 8px;
            }}
            QPushButton:hover {{ background-color: {C['warn']}44; }}
        """)
        chart_row.addWidget(self._btn_calibrate, alignment=Qt.AlignVCenter)

        self._chart = _BarChart(_SIGNAL)
        chart_row.addWidget(self._chart, stretch=1)

        outer.addLayout(chart_row, stretch=2)

        # ── Bottom: Start + legend ────────────────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)

        self._btn_start = QPushButton(t("btn_start"))
        self._btn_start.setObjectName("btn_start")
        self._btn_start.setFixedHeight(52)
        self._btn_start.setMinimumWidth(130)
        bottom_row.addWidget(self._btn_start)

        bottom_row.addSpacing(20)

        self._legend_lbls: list[tuple[str, QLabel]] = []
        for color, key in zip(_LEGEND_COLORS, _LEGEND_KEYS):
            box = QLabel()
            box.setFixedSize(_LEGEND_BOX, _LEGEND_BOX)
            box.setStyleSheet(
                f"background-color:{color};border:1px solid #ffffff33;border-radius:3px;"
            )
            txt = QLabel(t(key))
            txt.setStyleSheet(
                f"color:{C['text']};font-size:{_LEGEND_FONT}px;background:transparent;"
            )
            self._legend_lbls.append((key, txt))

            item = QWidget()
            item.setStyleSheet("background:transparent;")
            item_lay = QHBoxLayout(item)
            item_lay.setContentsMargins(0, 0, 0, 0)
            item_lay.setSpacing(6)
            item_lay.addWidget(box)
            item_lay.addWidget(txt)
            bottom_row.addWidget(item)

        bottom_row.addStretch()
        outer.addLayout(bottom_row)

        i18n.language_changed.connect(self.retranslate)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def retranslate(self):
        self._dur_bar.retranslate()
        self._btn_calibrate.setText(t("sq_btn_calibrate"))
        self._btn_start.setText(t("btn_start"))
        for key, lbl in self._legend_lbls:
            lbl.setText(t(key))
