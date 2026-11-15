"""Trends screen — three-tab view of global and regional aeration trends.

Tab 1: Global aeration trend (Σ LI waveform + bar chart).
Tab 2: Regional aeration trend — ROI 1-4 (R) or ROI 5-8 (L), toggled.
Tab 3: All trends — combined long-term view with lung icons.

Layout per tab (tabs 1 & 2):
  ┌─[wave panel, ~44%]──────┬─[bar charts, ~56%]──────────┐
  │  stacked waveforms       │  ΔZ,% header                 │
  │                          │  label | bar chart | % box   │
  ├─[table + N,% boxes]──────┤  …                           │
  └──────────────────────────┴──────────────────────────────┘
  [Старт] [Масштаб] [Маркер событий] … [Выход]
"""

from uuid import UUID

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QSizePolicy, QComboBox, QSlider, QScrollArea,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath

from ..application import (
    EngineeringSettings, EngineeringSettingsService, EventMarkerService,
    MonitoringData, TrendService,
)
from ..domain import EventCategory, StudyStatus
from ..application.monitoring import DISPLAY_WINDOW_SEC, DISPLAY_SAMPLES, BREATHS_IN_WINDOW
from ..waveform_draw import draw_filled_waveform
from ..styles import (
    C, AERATION_COLOR_T, AERATION_COLOR_R, AERATION_COLOR_L,
    AERATION_ROI_R, AERATION_ROI_L,
    configure_event_marker_btn, EVENT_MARKER_BTN_HEIGHT, EVENT_MARKER_BTN_MIN_WIDTH,
    TAB_BAR_FONT, TAB_BAR_SUB_FONT, FONT_BTN, FONT_LABEL, FONT_SMALL, FONT_VALUE,
    FONT_MEDICAL_VALUE,
)
from ..i18n import t, i18n
from ..ui_text import study_status_text


# ── Typography (12″ display) — из styles + локальные акценты ─────────────────
_TREND_LABEL = FONT_LABEL
_TREND_VALUE = FONT_VALUE
_TREND_DIM   = FONT_SMALL
_TREND_CH_PT = 16
_TREND_AXIS_PT = 14
_TREND_TABLE_PT = 22
_AMBER    = "#f9a825"
_AMBER_DK = "#3a2e00"
_CYAN     = "#00bcd4"
_CYAN_DIM = "#004d5a"

_GLOBAL_TREND_METRICS = (
    ("EELI", "eeli_au", ""),
    ("EILI", "eili_au", ""),
    ("TVi", "tvi_au", ""),
    ("MLI", "mli_au", ""),
    ("MVi", "mvi_au_per_min", ""),
    ("RR", "rr_bpm", "bpm"),
    ("R/L", "right_left_ratio", ""),
    ("V/D", "ventral_dorsal_ratio", ""),
)
def _regional_trend_metrics(roi_count: int) -> tuple[tuple[str, str, str], ...]:
    return (
        ("R", "right_percent", "%"),
        ("L", "left_percent", "%"),
        *(
            (f"TVi ROI {index}", f"roi_{index}_tvi_au", "")
            for index in range(1, roi_count + 1)
        ),
        *(
            (f"ROI {index}", f"roi_{index}_percent", "%")
            for index in range(1, roi_count + 1)
        ),
    )


_REGIONAL_TREND_METRICS = _regional_trend_metrics(8)
_CALCULATED_TREND_METRICS = _GLOBAL_TREND_METRICS + _REGIONAL_TREND_METRICS
_TREND_COLORS = (
    AERATION_COLOR_T, AERATION_COLOR_R, AERATION_COLOR_L, _CYAN,
    "#ffb74d", "#ba68c8", "#4dd0e1", "#aed581",
)


# ── Channel definitions ───────────────────────────────────────────────────────
_GLOBAL_CH = [("Σ LI", AERATION_COLOR_T)]
_RIGHT_CH  = [
    ("R",     AERATION_COLOR_R),
    ("ROI_1", AERATION_ROI_R[0]),
    ("ROI_2", AERATION_ROI_R[1]),
    ("ROI_3", AERATION_ROI_R[2]),
    ("ROI_4", AERATION_ROI_R[3]),
]
_LEFT_CH   = [
    ("L",     AERATION_COLOR_L),
    ("ROI_5", AERATION_ROI_L[0]),
    ("ROI_6", AERATION_ROI_L[1]),
    ("ROI_7", AERATION_ROI_L[2]),
    ("ROI_8", AERATION_ROI_L[3]),
]
# Первый канал (всё лёгкое) — в 2 раза выше каждого ROI
_REGIONAL_ROW_WEIGHTS = [2, 1, 1, 1, 1]


def _regional_channels(side: str, roi_count: int) -> list[tuple[str, str]]:
    bands = roi_count // 2
    start = 0 if side == "R" else bands
    colors = AERATION_ROI_R if side == "R" else AERATION_ROI_L
    aggregate = AERATION_COLOR_R if side == "R" else AERATION_COLOR_L
    return [
        (side, aggregate),
        *(
            (f"ROI_{start + index + 1}", colors[index % len(colors)])
            for index in range(bands)
        ),
    ]


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _empty_bars(n: int = BREATHS_IN_WINDOW) -> np.ndarray:
    return np.zeros(n, dtype=float)


def _format_elapsed(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}ч"
    if minutes:
        return f"{minutes}:{secs:02d}м"
    return f"{secs}с"


def _relative_percent(values: np.ndarray, baseline: float | None = None) -> np.ndarray:
    """Express a persisted ΔZ series relative to its first valid level."""
    result = np.asarray(values, dtype=float).copy()
    finite = result[np.isfinite(result)]
    if finite.size == 0:
        return result
    reference = float(finite[0]) if baseline is None else float(baseline)
    scale = abs(reference)
    if scale < 1e-9:
        scale = max(float(np.median(np.abs(finite))), 1e-9)
    result[np.isfinite(result)] = (
        result[np.isfinite(result)] - reference
    ) / scale * 100.0
    return result


def _trend_median_factor(mode: str, window_seconds: int) -> int:
    if mode == "manual_infant":
        for threshold, factor in (
            (86400, 243), (21600, 81), (3600, 27), (1800, 9), (900, 3)
        ):
            if window_seconds >= threshold:
                return factor
    elif mode == "manual_adult":
        for threshold, factor in ((86400, 27), (21600, 9), (1800, 3)):
            if window_seconds >= threshold:
                return factor
    return 1


def _median_reduce(values: np.ndarray, factor: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if factor <= 1 or values.size == 0:
        return values
    reduced = []
    for start in range(0, values.size, factor):
        group = values[start:start + factor]
        reduced.append(float(np.median(group)) if np.all(np.isfinite(group)) else np.nan)
    return np.asarray(reduced, dtype=float)


def _last_reduce(values: np.ndarray, factor: int) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if factor <= 1 or values.size == 0:
        return values
    return np.asarray([
        values[min(start + factor, values.size) - 1]
        for start in range(0, values.size, factor)
    ], dtype=float)


# ── Separator helpers ─────────────────────────────────────────────────────────

def _vsep(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"color:{C['border']};max-width:1px;")
    return f


def _hsep(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{C['border']};max-height:1px;")
    return f


# ════════════════════════════════════════════════════════════════════════════════
# Primitive paint widgets
# ════════════════════════════════════════════════════════════════════════════════

class _BarChart(QWidget):
    """Signed relative-change bars with a data-driven symmetric scale."""

    def __init__(self, seed: int = 0, compact: bool = False, parent=None):
        super().__init__(parent)
        self._data = _empty_bars()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setMinimumHeight(30 if compact else 46)

    def set_data(self, data: np.ndarray):
        self._data = data
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(C["bg_wave"]))

        w, h = self.width(), self.height()
        n = len(self._data)
        if n == 0:
            return

        # ml wider for Y-axis labels; mt wider for Y title
        ml, mr, mt, mb = 36, 4, 8, 18
        pw = w - ml - mr
        ph = h - mt - mb
        if ph < 1 or pw < 1:
            return

        f = p.font()
        f.setPointSize(_TREND_AXIS_PT)
        p.setFont(f)

        finite = self._data[np.isfinite(self._data)]
        max_v = max(1.0, float(np.max(np.abs(finite))) if finite.size else 1.0)

        # ── Signed Y-axis grid and labels ────────────────────────────────────
        for frac, value in ((0.0, max_v), (0.5, 0.0), (1.0, -max_v)):
            gy = int(mt + frac * ph)
            p.setPen(QPen(QColor(C["border"]), 1, Qt.DotLine))
            p.drawLine(ml, gy, ml + pw, gy)
            p.setPen(QPen(QColor(C["text_lo"])))
            p.drawText(0, gy + 3, f"{value:.0f}")

        # ── Bars ─────────────────────────────────────────────────────────────
        bw = pw / n
        gap = max(1.0, bw * 0.18)
        for i, v in enumerate(self._data):
            if not np.isfinite(v):
                continue
            x = ml + i * bw + gap / 2
            bar_w = bw - gap
            zero_y = mt + ph / 2
            bh = max(1.0, abs(float(v)) / max_v * ph / 2)
            y = zero_y - bh if v >= 0 else zero_y
            clr = QColor(_CYAN) if i == n - 1 else QColor(_CYAN_DIM)
            p.fillRect(int(x), int(y), max(1, int(bar_w)), int(bh), clr)
            p.setPen(QPen(QColor(_CYAN), 1))
            p.drawLine(int(x), int(y), int(x + bar_w), int(y))

        # ── Border ───────────────────────────────────────────────────────────
        p.setPen(QPen(QColor(C["border"]), 1))
        p.drawRect(ml, mt, pw - 1, ph)


class _BarRow(QWidget):
    """label | _BarChart | % box — one trend channel row."""

    def __init__(self, label: str, color: str, seed: int = 0, compact: bool = False, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(48 if compact else 72)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1 if compact else 2, 2, 1 if compact else 2)
        lay.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFixedWidth(80)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_font = _TREND_LABEL - 2 if compact else _TREND_LABEL
        lbl.setStyleSheet(
            f"color:{color};font-size:{lbl_font}px;font-weight:bold;background:transparent;"
        )
        lay.addWidget(lbl)

        self.chart = _BarChart(seed=seed, compact=compact)
        lay.addWidget(self.chart, stretch=1)

        self.lbl_pct = QLabel("0")
        self.lbl_pct.setFixedWidth(82)
        self.lbl_pct.setAlignment(Qt.AlignCenter)
        pct_font = 26 if compact else FONT_MEDICAL_VALUE
        self.lbl_pct.setStyleSheet(f"""
            background:{C['bg_card']};color:{C['text']};
            border:1px solid {C['border']};border-radius:3px;
            font-size:{pct_font}px;font-weight:bold;
        """)
        lay.addWidget(self.lbl_pct)

        data = self.chart._data
        self.lbl_pct.setText(f"{data[-1]:.0f}%")

    def refresh(self, data: np.ndarray | None = None):
        if data is None:
            return
        values = np.asarray(data, dtype=float)
        values = values[np.isfinite(values)]
        if values.size > BREATHS_IN_WINDOW:
            values = values[-BREATHS_IN_WINDOW:]
        self.chart.set_data(values)
        self.lbl_pct.setText("—" if values.size == 0 else f"{values[-1]:.1f}")


class _MultiWave(QWidget):
    """Stacked waveform display — all channels in one QPainter."""

    def __init__(
        self,
        channels: list[tuple[str, str]],
        weights: list[int] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._channels = channels
        n = len(channels)
        if weights is None or len(weights) != n:
            self._weights = [1] * n
        else:
            self._weights = list(weights)
        self._data: list[np.ndarray] = [np.zeros(DISPLAY_SAMPLES) for _ in channels]
        self._times = np.asarray([], dtype=float)
        self._axis_start = 0.0
        self._axis_end = float(DISPLAY_WINDOW_SEC)
        self._markers: tuple[float, ...] = ()
        self._bad_intervals: tuple[tuple[float, float], ...] = ()
        self._plot_left_margin = 58
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_channels(self, channels: list[tuple[str, str]]) -> None:
        self._channels = list(channels)
        self._weights = [1] * len(channels)
        self.update()

    def set_data(
        self,
        data_list: list[np.ndarray],
        time_values=None,
        axis_range: tuple[float, float] | None = None,
    ):
        self._data = list(data_list)
        self._times = np.asarray(time_values if time_values is not None else [], dtype=float)
        if axis_range is not None and axis_range[1] > axis_range[0]:
            self._axis_start, self._axis_end = map(float, axis_range)
        self.update()

    def set_quality_intervals(self, intervals) -> None:
        self._bad_intervals = tuple(
            (float(start), float(end)) for start, end in intervals
        )
        self.setToolTip(
            t("monitor_quality_degraded") if self._bad_intervals else ""
        )
        self.update()

    def set_event_markers(self, events, time_values):
        times = np.asarray(time_values, dtype=float)
        start, end = self._axis_start, self._axis_end
        if times.size == 1:
            self._markers = tuple(
                (float(event.position_seconds) - start) / (end - start)
                for event in events if start <= float(event.position_seconds) <= end
            )
        else:
            span = end - start
            self._markers = tuple(
                min(1.0, (float(event.position_seconds) - start) / span)
                for event in events
                if start <= float(event.position_seconds) <= end
            )
        self.update()

    def _channel_heights(self, tot_h: float) -> list[float]:
        total_w = sum(self._weights)
        return [tot_h * w / total_w for w in self._weights]

    def paintEvent(self, _):  # noqa: C901
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(C["bg_wave"]))

        w, h = self.width(), self.height()
        n_ch = len(self._channels)
        if n_ch == 0:
            return

        base_font = p.font()
        label_font = p.font()
        label_font.setPointSize(_TREND_CH_PT)
        label_font.setBold(True)
        p.setFont(label_font)
        label_metrics = p.fontMetrics()
        longest_label = max(
            (label_metrics.horizontalAdvance(label) for label, _color in self._channels),
            default=40,
        )
        ML, MR, MT, MB = max(58, longest_label + 18), 4, 16, 20
        self._plot_left_margin = ML
        p.setFont(base_font)
        pw = w - ML - MR
        tot_h = h - MT - MB
        ch_heights = self._channel_heights(tot_h)

        # channel separator grid lines
        p.setPen(QPen(QColor(C["border"]), 1, Qt.DotLine))
        y_off = MT
        for i in range(1, n_ch):
            y_off += ch_heights[i - 1]
            p.drawLine(ML, int(y_off), ML + pw, int(y_off))

        # outer border
        p.setPen(QPen(QColor(C["border"]), 1))
        p.drawRect(ML, MT, pw, int(tot_h))

        axis_span = self._axis_end - self._axis_start
        p.setBrush(QBrush(QColor(120, 35, 35, 90)))
        p.setPen(Qt.NoPen)
        for bad_start, bad_end in self._bad_intervals:
            x1 = ML + (bad_start - self._axis_start) / axis_span * pw
            x2 = ML + (bad_end - self._axis_start) / axis_span * pw
            p.drawRect(int(max(ML, x1)), MT, max(1, int(x2 - x1)), int(tot_h))

        # Actual selected time range.
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            value = self._axis_start + fraction * axis_span
            lbl = _format_elapsed(value)
            tx = int(ML + fraction * pw)
            p.setPen(QPen(QColor(C["border"]), 1))
            p.drawLine(tx, MT + int(tot_h), tx, MT + int(tot_h) + 3)
            p.setPen(QPen(QColor(C["text_lo"])))
            offset = -p.fontMetrics().horizontalAdvance(lbl) if fraction == 1.0 else 0
            p.drawText(tx + offset, h - 2, lbl)

        # waveform traces
        ch_top = MT
        for ci, (label, color) in enumerate(self._channels):
            ch_h = ch_heights[ci]
            is_compact = self._weights[ci] < max(self._weights)

            p.setPen(QPen(QColor(color)))
            f = p.font()
            f.setPointSize(_TREND_CH_PT - 2 if is_compact else _TREND_CH_PT)
            f.setBold(True)
            p.setFont(f)
            p.drawText(2, int(ch_top + ch_h * 0.62), label)

            data = self._data[ci] if ci < len(self._data) else np.zeros(2)
            n = len(data)
            if n >= 2:
                finite = data[np.isfinite(data)]
                if finite.size == 0:
                    ch_top += ch_h
                    continue
                lo, hi = float(finite.min()), float(finite.max())
                if hi - lo < 1e-9:
                    hi = lo + 1.0

                mid_y = ch_top + ch_h / 2
                p.setPen(QPen(QColor(C["border"]), 1, Qt.DotLine))
                p.drawLine(ML, int(mid_y), ML + pw, int(mid_y))

                pad = 3 if is_compact else 4
                baseline = ch_top + ch_h - pad
                segment_x, segment_y = [], []
                times = self._times if self._times.size == n else np.linspace(
                    self._axis_start, self._axis_end, n
                )
                for i in range(n + 1):
                    value = data[i] if i < n else np.nan
                    if np.isfinite(value):
                        x_fraction = (float(times[i]) - self._axis_start) / axis_span
                        segment_x.append(ML + max(0.0, min(1.0, x_fraction)) * pw)
                        segment_y.append(
                            ch_top + pad + (1.0 - (value - lo) / (hi - lo)) * (ch_h - 2 * pad)
                        )
                    elif len(segment_x) >= 2:
                        draw_filled_waveform(p, segment_x, segment_y, QColor(color), baseline)
                        segment_x, segment_y = [], []
                    else:
                        segment_x, segment_y = [], []

            ch_top += ch_h

        p.setPen(QPen(QColor(C["warn"]), 2, Qt.DashLine))
        for position in self._markers:
            marker_x = ML + max(0.0, min(1.0, position)) * pw
            p.drawLine(int(marker_x), MT, int(marker_x), MT + int(tot_h))


class _TrendTable(QWidget):
    """Recent persisted values for the visible channels."""

    N_COLS, N_ROWS = 6, 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(100, 50)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self._vals = [["—"] * self.N_COLS for _ in range(self.N_ROWS)]

    def set_values(self, values):
        rows = list(values)
        self._vals = [
            [f"{value:.1f}" if value is not None else "—" for value in row[:self.N_COLS]]
            + ["—"] * max(0, self.N_COLS - len(row))
            for row in rows[:self.N_ROWS]
        ]
        self._vals += [["—"] * self.N_COLS] * max(0, self.N_ROWS - len(self._vals))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(C["bg_wave"]))
        w, h = self.width(), self.height()
        cw = w / self.N_COLS
        rh = h / self.N_ROWS

        p.setPen(QPen(QColor(C["border"]), 1))
        for r in range(self.N_ROWS + 1):
            p.drawLine(0, int(r * rh), w, int(r * rh))
        for c in range(self.N_COLS + 1):
            p.drawLine(int(c * cw), 0, int(c * cw), h)

        p.setPen(QPen(QColor(C["text_dim"])))
        f = p.font()
        f.setPointSize(_TREND_TABLE_PT)
        p.setFont(f)
        for r in range(self.N_ROWS):
            for c in range(self.N_COLS):
                p.drawText(int(c * cw + cw * 0.2), int(r * rh + rh * 0.68),
                           str(self._vals[r][c]))


class _LungIcon(QWidget):
    """Tiny paired L/R lung icon showing fill level."""

    def __init__(self, l_fill: float = 0.5, r_fill: float = 0.55, parent=None):
        super().__init__(parent)
        self._l = l_fill
        self._r = r_fill
        self.setFixedSize(72, 90)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(C["bg_panel"]))

        w, h = self.width(), self.height()
        cx = w // 2
        lw = int(cx * 0.78)
        lh = int(h * 0.72)
        top = int(h * 0.08)
        gap = 3

        for side, fill, color_key in [
            ("L", self._l, "lung_left"),
            ("R", self._r, "lung_right"),
        ]:
            if side == "L":
                ex = cx - gap - lw
            else:
                ex = cx + gap

            path = QPainterPath()
            path.addEllipse(ex, top, lw, lh)
            p.setPen(QPen(QColor(C["border"]), 1))
            p.setBrush(QBrush(QColor(C["bg_card"])))
            p.drawPath(path)
            p.save()
            p.setClipPath(path)
            fill_height = int(lh * max(0.0, min(1.0, fill)))
            p.fillRect(
                ex, top + lh - fill_height, lw, fill_height,
                QColor(C[color_key]),
            )
            p.restore()
            p.setPen(QPen(QColor(C["border"]), 1))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

            p.setPen(QPen(QColor(C["text_dim"])))
            f = p.font()
            f.setPointSize(FONT_SMALL)
            p.setFont(f)
            p.drawText(ex + 4, top + lh + 12, side)

    def set_fill(self, left: float, right: float):
        self._l = max(0.0, min(1.0, left))
        self._r = max(0.0, min(1.0, right))
        self.update()


# ════════════════════════════════════════════════════════════════════════════════
# Shared layout helpers
# ════════════════════════════════════════════════════════════════════════════════

def _bar_header() -> QWidget:
    """ΔZ,% … Тренд header row above bar charts."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 2, 4, 0)
    dz = QLabel(t("trends_dz"))
    dz.setStyleSheet(
        f"color:{C['text_dim']};font-size:{_TREND_LABEL}px;font-weight:bold;background:transparent;"
    )
    tr = QLabel(t("trends_trend"))
    tr.setAlignment(Qt.AlignRight)
    tr.setStyleSheet(
        f"color:{C['text_dim']};font-size:{_TREND_LABEL}px;background:transparent;"
    )
    lay.addWidget(dz)
    lay.addStretch()
    lay.addWidget(tr)
    return w


class _SummaryColumn(QWidget):
    """Min/median/max summary for the selected persisted series."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addStretch()
        self.boxes = []
        for label_text in ("min,%", "med,%", "max,%"):
            row = QWidget()
            r = QHBoxLayout(row)
            r.setContentsMargins(0, 0, 0, 0)
            r.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color:{C['text_dim']};font-size:{_TREND_VALUE}px;background:transparent;"
            )
            box = QLabel("—")
            box.setFixedSize(84, 40)
            box.setAlignment(Qt.AlignCenter)
            box.setStyleSheet(
                f"background:{C['bg_card']};border:1px solid {C['border']};"
                f"color:{C['text']};font-size:{FONT_MEDICAL_VALUE}px;font-weight:bold;"
            )
            r.addWidget(lbl)
            r.addWidget(box)
            lay.addWidget(row)
            self.boxes.append(box)
        lay.addStretch()

    def set_values(self, values) -> None:
        finite = np.asarray(values, dtype=float)
        finite = finite[np.isfinite(finite)]
        summaries = () if finite.size == 0 else (
            float(np.min(finite)), float(np.median(finite)), float(np.max(finite))
        )
        for index, box in enumerate(self.boxes):
            box.setText("—" if not summaries else f"{summaries[index]:.1f}")


class _TableBlock(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lbl = QLabel(t("trends_table"))
        lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:{_TREND_LABEL}px;background:transparent;"
        )
        self.table = _TrendTable()
        lay.addWidget(lbl)
        lay.addWidget(self.table, stretch=1)


def _npct_col() -> _SummaryColumn:
    """Compatibility helper returning a real summary widget."""
    return _SummaryColumn()


def _table_block() -> _TableBlock:
    """Table label and populated grid."""
    return _TableBlock()


# ════════════════════════════════════════════════════════════════════════════════
# Left panel: waveform + table block
# ════════════════════════════════════════════════════════════════════════════════

class _LeftPanel(QWidget):
    """Waveform on top, table + N,% row at the bottom."""

    def __init__(
        self,
        channels: list[tuple[str, str]],
        channel_weights: list[int] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.wave = _MultiWave(channels, weights=channel_weights)
        lay.addWidget(self.wave, stretch=3)

        lay.addWidget(_hsep())

        bottom = QWidget()
        b_lay = QHBoxLayout(bottom)
        b_lay.setContentsMargins(4, 2, 4, 2)
        b_lay.setSpacing(8)
        self.table_block = _table_block()
        self.summary = _npct_col()
        b_lay.addWidget(self.table_block, stretch=1)
        b_lay.addWidget(self.summary)
        lay.addWidget(bottom, stretch=1)

    def refresh_details(self, data_list: list[np.ndarray]) -> None:
        self.table_block.table.set_values([
            list(np.asarray(values, dtype=float)[-6:]) for values in data_list[:5]
        ])
        self.summary.set_values(data_list[0] if data_list else ())


# ════════════════════════════════════════════════════════════════════════════════
# Right panel: bar charts
# ════════════════════════════════════════════════════════════════════════════════

class _RightPanel(QWidget):
    """ΔZ,% header + one _BarRow per channel."""

    def __init__(
        self,
        channels: list[tuple[str, str]],
        row_weights: list[int] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(2)
        lay.addWidget(_bar_header())

        self.bar_rows: list[_BarRow] = []
        regional = row_weights is not None and len(row_weights) == len(channels)
        for i, (label, color) in enumerate(channels):
            seed = i * 31 + sum(ord(c) for c in label)
            stretch = row_weights[i] if regional else 1
            row = _BarRow(label, color, seed=seed, compact=regional and i > 0)
            lay.addWidget(row, stretch=stretch)
            self.bar_rows.append(row)

    def refresh(self, data_list=None):
        if data_list is None:
            return
        for row, data in zip(self.bar_rows, data_list):
            row.refresh(np.asarray(data, dtype=float))


# ── Panel width ratio: left waveform vs right bar charts ─────────────────────
_LEFT_STRETCH  = 11
_RIGHT_STRETCH = 14


def _size_bottom_btn(btn: QPushButton) -> None:
    """Единый размер кнопок нижней панели (как у маркера событий)."""
    btn.setFixedHeight(EVENT_MARKER_BTN_HEIGHT)
    btn.setMinimumWidth(EVENT_MARKER_BTN_MIN_WIDTH)
    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class _GlobalTab(QWidget):
    """Tab 1: Global aeration trend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        self.left  = _LeftPanel(_GLOBAL_CH)
        self.right = _RightPanel([("Σ LI", AERATION_COLOR_T)])
        lay.addWidget(self.left,  stretch=_LEFT_STRETCH)
        lay.addWidget(_vsep())
        lay.addWidget(self.right, stretch=_RIGHT_STRETCH)

    def refresh(self, waves: dict):
        self.left.wave.set_data(
            [waves["global"]], waves["time"], waves["axis_range"]
        )
        self.left.refresh_details([waves["global"]])
        self.right.refresh([waves["cycles"]["global"]])


class _RegionalPage(QWidget):
    """One side (R or L) for the regional tab."""

    def __init__(self, channels: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        weights = [2, *([1] * (len(channels) - 1))]
        self.left  = _LeftPanel(channels, channel_weights=weights)
        self.right = _RightPanel(channels, row_weights=weights)
        lay.addWidget(self.left,  stretch=_LEFT_STRETCH)
        lay.addWidget(_vsep())
        lay.addWidget(self.right, stretch=_RIGHT_STRETCH)

    def refresh(
        self, wave_list: list[np.ndarray], times, axis_range, bar_list=None
    ):
        self.left.wave.set_data(wave_list, times, axis_range)
        self.left.refresh_details(wave_list)
        self.right.refresh(bar_list if bar_list is not None else wave_list)


class _RegionalTab(QWidget):
    """Tab 2: Regional aeration trend — R / L toggle."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._side = "R"
        self._roi_count = 8

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # R / L toggle buttons
        tgl = QWidget()
        tgl.setFixedHeight(48)
        tgl_lay = QHBoxLayout(tgl)
        tgl_lay.setContentsMargins(6, 4, 6, 4)
        tgl_lay.setSpacing(6)
        self.btn_r = QPushButton(t("trends_right_short"))
        self.btn_l = QPushButton(t("trends_left_short"))
        for btn in (self.btn_r, self.btn_l):
            btn.setFixedHeight(38)
        self.btn_r.clicked.connect(lambda: self._switch("R"))
        self.btn_l.clicked.connect(lambda: self._switch("L"))
        tgl_lay.addWidget(self.btn_r)
        tgl_lay.addWidget(self.btn_l)
        tgl_lay.addStretch()
        outer.addWidget(tgl)
        outer.addWidget(_hsep())

        self.stack = QStackedWidget()
        self.page_r = _RegionalPage(_regional_channels("R", self._roi_count))
        self.page_l = _RegionalPage(_regional_channels("L", self._roi_count))
        self.stack.addWidget(self.page_r)
        self.stack.addWidget(self.page_l)
        outer.addWidget(self.stack, stretch=1)

        self._update_toggle()
        i18n.language_changed.connect(self.retranslate)

    def _switch(self, side: str):
        self._side = side
        self.stack.setCurrentIndex(0 if side == "R" else 1)
        self._update_toggle()

    def _active_style(self) -> str:
        return (f"QPushButton{{background:{_AMBER};color:#000;"
                f"border:1px solid #c77800;border-radius:3px;"
                f"font-size:{TAB_BAR_SUB_FONT}px;font-weight:bold;padding:4px 12px;}}")

    def _inactive_style(self) -> str:
        return (f"QPushButton{{background:{_AMBER_DK};color:{_AMBER};"
                f"border:1px solid #5a4800;border-radius:3px;"
                f"font-size:{TAB_BAR_SUB_FONT}px;padding:4px 12px;}}"
                f"QPushButton:hover{{background:#4a3c00;}}")

    def _update_toggle(self):
        self.btn_r.setStyleSheet(self._active_style() if self._side == "R" else self._inactive_style())
        self.btn_l.setStyleSheet(self._active_style() if self._side == "L" else self._inactive_style())

    def refresh(self, waves: dict):
        rois = waves["rois"]
        roi_count = len(rois)
        if roi_count >= 2 and roi_count % 2 == 0 and roi_count != self._roi_count:
            self._set_roi_count(roi_count)
        bands = self._roi_count // 2
        r_data = [waves.get("r", np.sum(rois[:bands], axis=0)), *rois[:bands]]
        l_data = [waves.get("l", np.sum(rois[bands:], axis=0)), *rois[bands:]]
        cycle_rois = waves["cycles"]["rois"]
        r_cycles = [waves["cycles"]["r"], *cycle_rois[:bands]]
        l_cycles = [waves["cycles"]["l"], *cycle_rois[bands:]]
        self.page_r.refresh(
            r_data, waves["time"], waves["axis_range"], r_cycles
        )
        self.page_l.refresh(
            l_data, waves["time"], waves["axis_range"], l_cycles
        )

    def _set_roi_count(self, roi_count: int) -> None:
        self._roi_count = roi_count
        old_r, old_l = self.page_r, self.page_l
        self.page_r = _RegionalPage(_regional_channels("R", roi_count))
        self.page_l = _RegionalPage(_regional_channels("L", roi_count))
        self.stack.removeWidget(old_r)
        self.stack.removeWidget(old_l)
        old_r.deleteLater()
        old_l.deleteLater()
        self.stack.addWidget(self.page_r)
        self.stack.addWidget(self.page_l)
        self.stack.setCurrentIndex(0 if self._side == "R" else 1)

    def retranslate(self):
        self.btn_r.setText(t("trends_right_short"))
        self.btn_l.setText(t("trends_left_short"))


class _AllTrendsTab(QWidget):
    """Tab 3: Global + Regional combined long-term view."""

    def __init__(self, parent=None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        # ── Upper section ─────────────────────────────────────────────────────
        upper = QWidget()
        u_lay = QHBoxLayout(upper)
        u_lay.setContentsMargins(0, 0, 0, 0)
        u_lay.setSpacing(8)

        self.global_params = self._param_section(
            "trends_global_label", AERATION_COLOR_T, ("last,%", "med,%")
        )
        u_lay.addWidget(self.global_params, stretch=1)
        u_lay.addWidget(_vsep())
        self.regional_params = self._param_section(
            "trends_reg_label", AERATION_COLOR_R, ("R,%", "L,%")
        )
        u_lay.addWidget(self.regional_params, stretch=1)
        u_lay.addWidget(_vsep())

        # Lung icons (3 temporal snapshots) — fixed height so they don't stretch
        icons = QWidget()
        icons.setMaximumHeight(110)
        icons_lay = QHBoxLayout(icons)
        icons_lay.setContentsMargins(4, 8, 4, 8)
        icons_lay.setSpacing(6)
        icons_lay.setAlignment(Qt.AlignVCenter)
        self.lung_icons = []
        for lf, rf in [(0.0, 0.0)] * 3:
            icon = _LungIcon(lf, rf)
            icons_lay.addWidget(icon, alignment=Qt.AlignVCenter)
            self.lung_icons.append(icon)
        u_lay.addWidget(icons, stretch=1)
        u_lay.addWidget(_vsep())

        self.table_block = _table_block()
        u_lay.addWidget(self.table_block, stretch=2)
        u_lay.addWidget(_vsep())

        # Right: single global bar chart + "Время, часы" label
        bar_col = QWidget()
        bc_lay = QVBoxLayout(bar_col)
        bc_lay.setContentsMargins(4, 0, 4, 0)
        bc_lay.setSpacing(2)
        dz = QLabel(t("trends_dz"))
        dz.setStyleSheet(
            f"color:{C['text_dim']};font-size:{_TREND_LABEL}px;font-weight:bold;background:transparent;"
        )
        bc_lay.addWidget(dz)
        self.main_bar = _BarRow("Σ LI", AERATION_COLOR_T, seed=9001)
        bc_lay.addWidget(self.main_bar, stretch=1)
        hrs = QLabel(t("trends_time"))
        hrs.setAlignment(Qt.AlignCenter)
        hrs.setStyleSheet(
            f"color:{C['text_lo']};font-size:{_TREND_DIM}px;background:transparent;"
        )
        bc_lay.addWidget(hrs)
        u_lay.addWidget(bar_col, stretch=2)

        outer.addWidget(upper, stretch=1)
        outer.addWidget(_hsep())

        # ── Lower section: long-term waveform ────────────────────────────────
        lower = QWidget()
        l_lay = QVBoxLayout(lower)
        l_lay.setContentsMargins(0, 0, 0, 0)
        l_lay.setSpacing(2)

        hdr = QWidget()
        h_lay = QHBoxLayout(hdr)
        h_lay.setContentsMargins(4, 0, 4, 0)
        lbl_t = QLabel("T")
        lbl_t.setStyleSheet(
            f"color:{AERATION_COLOR_T};font-size:{_TREND_LABEL + 2}px;font-weight:bold;background:transparent;"
        )
        h_lay.addWidget(lbl_t)
        h_lay.addStretch()
        l_lay.addWidget(hdr)

        self.long_wave = _MultiWave([("T", AERATION_COLOR_T)])
        self.long_wave.setMinimumHeight(80)
        l_lay.addWidget(self.long_wave, stretch=1)

        time_lbl = QLabel(t("trends_time"))
        time_lbl.setAlignment(Qt.AlignCenter)
        time_lbl.setStyleSheet(
            f"color:{C['text_lo']};font-size:{_TREND_DIM}px;background:transparent;"
        )
        l_lay.addWidget(time_lbl)

        outer.addWidget(lower, stretch=1)

    def _param_section(
        self, title_key: str, color: str, labels: tuple[str, str]
    ) -> QWidget:
        box = QWidget()
        box.value_boxes = []
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)
        lbl = QLabel(t(title_key))
        lbl.setStyleSheet(
            f"color:{color};font-size:{_TREND_LABEL}px;font-weight:bold;background:transparent;"
        )
        lay.addWidget(lbl)
        for label_text in labels:
            row = QWidget()
            r = QHBoxLayout(row)
            r.setContentsMargins(0, 0, 0, 0)
            r.setSpacing(4)
            l2 = QLabel(label_text)
            l2.setStyleSheet(
                f"color:{C['text_dim']};font-size:{_TREND_VALUE}px;background:transparent;"
            )
            b2 = QLabel("—")
            b2.setFixedSize(76, 40)
            b2.setAlignment(Qt.AlignCenter)
            b2.setStyleSheet(
                f"background:{C['bg_card']};border:1px solid {C['border']};"
                f"color:{C['text']};font-size:{FONT_MEDICAL_VALUE}px;font-weight:bold;"
            )
            r.addWidget(l2)
            r.addWidget(b2)
            lay.addWidget(row)
            box.value_boxes.append(b2)
        lay.addStretch()
        return box

    def refresh(self, waves: dict):
        self.long_wave.set_data(
            [waves["global"]], waves["time"], waves["axis_range"]
        )
        self.main_bar.refresh(np.asarray(waves["cycles"]["global"], dtype=float))
        self.table_block.table.set_values([
            list(np.asarray(waves[name], dtype=float)[-6:])
            for name in ("global", "r", "l")
        ])
        global_values = np.asarray(waves["global"], dtype=float)
        global_finite = global_values[np.isfinite(global_values)]
        global_summary = (
            (float(global_finite[-1]), float(np.median(global_finite)))
            if global_finite.size else (None, None)
        )
        for label, value in zip(self.global_params.value_boxes, global_summary):
            label.setText("—" if value is None else f"{value:.1f}")
        regional_latest = []
        for name in ("r", "l"):
            values = np.asarray(waves[name], dtype=float)
            finite = values[np.isfinite(values)]
            regional_latest.append(float(finite[-1]) if finite.size else None)
        for label, value in zip(self.regional_params.value_boxes, regional_latest):
            label.setText("—" if value is None else f"{value:.1f}")
        right = np.asarray(waves.get("r_absolute", []), dtype=float)
        left = np.asarray(waves.get("l_absolute", []), dtype=float)
        valid = np.flatnonzero(np.isfinite(right) & np.isfinite(left))
        if valid.size:
            sample_indexes = np.linspace(0, valid.size - 1, len(self.lung_icons)).astype(int)
            for icon, sample_index in zip(self.lung_icons, sample_indexes):
                index = int(valid[sample_index])
                total = max(abs(float(right[index])) + abs(float(left[index])), 1e-9)
                icon.set_fill(
                    abs(float(left[index])) / total,
                    abs(float(right[index])) / total,
                )


class _MetricChartsTab(QWidget):
    """All requested metric charts at once, vertically scrollable when needed."""

    def __init__(self, metrics, parent=None):
        super().__init__(parent)
        self.metrics = tuple(metrics)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        channels = [
            (
                f"{label}, {unit}" if unit else label,
                _TREND_COLORS[index % len(_TREND_COLORS)],
            )
            for index, (label, _code, unit) in enumerate(self.metrics)
        ]
        self.wave = _MultiWave(channels)
        self.wave.setMinimumHeight(max(420, len(channels) * 92))

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.wave)
        layout.addWidget(self.scroll)

    def refresh(self, waves: dict) -> None:
        metric_values = waves.get("metrics", {})
        self.wave.set_data(
            [
                np.asarray(metric_values.get(code, ()), dtype=float)
                for _label, code, _unit in self.metrics
            ],
            waves["time"],
            waves["axis_range"],
        )


# ════════════════════════════════════════════════════════════════════════════════
# Tab bar
# ════════════════════════════════════════════════════════════════════════════════

class _TrendTabBar(QWidget):
    tab_changed = Signal(int)
    _KEYS = ["trends_tab_global", "trends_tab_regional", "trends_tab_all"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self._active = 0
        self._btns: list[QPushButton] = []

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        for i, key in enumerate(self._KEYS):
            btn = QPushButton(t(key))
            btn.clicked.connect(lambda _, idx=i: self._on(idx))
            self._btns.append(btn)
            lay.addWidget(btn, stretch=1)

        self._update_styles()
        i18n.language_changed.connect(self.retranslate)

    def _on(self, idx: int):
        self._active = idx
        self._update_styles()
        self.tab_changed.emit(idx)

    def _update_styles(self):
        for i, btn in enumerate(self._btns):
            if i == self._active:
                btn.setStyleSheet(f"""QPushButton {{
                    background:{_AMBER};color:#000000;
                    border:1px solid #c77800;border-bottom:2px solid {_AMBER};
                    font-size:{TAB_BAR_FONT}px;font-weight:bold;padding:6px 10px;
                }}""")
            else:
                btn.setStyleSheet(f"""QPushButton {{
                    background:{_AMBER_DK};color:{_AMBER};
                    border:1px solid #5a4800;
                    font-size:{TAB_BAR_FONT}px;padding:6px 10px;
                }}
                QPushButton:hover{{background:#4a3c00;}}""")

    def retranslate(self):
        for btn, key in zip(self._btns, self._KEYS):
            btn.setText(t(key))


# ════════════════════════════════════════════════════════════════════════════════
# Bottom toolbar
# ════════════════════════════════════════════════════════════════════════════════

class _BottomBar(QWidget):
    exit_clicked = Signal()

    _AMBER_BTN = f"""QPushButton {{
        background:{_AMBER};color:#000000;
        border:1px solid #c77800;border-radius:4px;
        font-size:{FONT_BTN}px;font-weight:600;padding:8px 20px;
    }}
    QPushButton:hover{{background:#ffa000;}}"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(EVENT_MARKER_BTN_HEIGHT + 12)
        self.setStyleSheet(f"background:{C['bg_panel']};border-top:1px solid {C['border']};")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        self.btn_start = QPushButton(t("btn_start"))
        self.btn_start.setStyleSheet(f"""QPushButton {{
            background:{C['ok']};color:white;border:1px solid #1b5e20;
            border-radius:4px;font-size:{FONT_BTN}px;font-weight:bold;padding:8px 20px;
        }} QPushButton:hover{{background:{C['ok_hover']};}}""")
        _size_bottom_btn(self.btn_start)
        lay.addWidget(self.btn_start, stretch=1)

        self._amber_btns: list[QPushButton] = []
        for key in ("trends_btn_scale",):
            btn = QPushButton(t(key))
            btn.setStyleSheet(self._AMBER_BTN)
            _size_bottom_btn(btn)
            lay.addWidget(btn, stretch=1)
            self._amber_btns.append(btn)

        self.btn_marker = QPushButton(t("wave_event_marker"))
        configure_event_marker_btn(self.btn_marker)
        _size_bottom_btn(self.btn_marker)
        lay.addWidget(self.btn_marker, stretch=1)

        btn_exit = QPushButton(t("trends_btn_exit"))
        btn_exit.setStyleSheet(self._AMBER_BTN)
        btn_exit.clicked.connect(self.exit_clicked)
        _size_bottom_btn(btn_exit)
        lay.addWidget(btn_exit, stretch=1)
        self._btn_exit = btn_exit

        i18n.language_changed.connect(self.retranslate)

    def retranslate(self):
        self.btn_start.setText(t("btn_start"))
        for btn, key in zip(self._amber_btns, ("trends_btn_scale",)):
            btn.setText(t(key))
        self.btn_marker.setText(t("wave_event_marker"))
        self._btn_exit.setText(t("trends_btn_exit"))


# ════════════════════════════════════════════════════════════════════════════════
# Main screen
# ════════════════════════════════════════════════════════════════════════════════

class TrendsScreen(QWidget):
    """Trends screen with three tabs and injected monitoring data."""

    def __init__(
        self,
        monitoring: MonitoringData,
        parent=None,
        *,
        marker_service: EventMarkerService | None = None,
        trend_service: TrendService | None = None,
        study_repository=None,
        event_repository=None,
        lifecycle=None,
        engineering_settings: EngineeringSettingsService | None = None,
    ):
        super().__init__(parent)
        self._monitoring = monitoring
        self._marker_service = marker_service
        self._trend_service = trend_service
        self._study_repository = study_repository
        self._event_repository = event_repository
        self._lifecycle = lifecycle
        self._roi_count = 8
        self._trend_point_mode = "interval"
        self._trend_downsampling_mode = "manual_adult"
        self._unsubscribe_engineering = None
        if engineering_settings is not None:
            self._unsubscribe_engineering = engineering_settings.subscribe(
                self._apply_engineering_settings
            )
            self._apply_engineering_settings(engineering_settings.current)
        self._study_ids: list[UUID] = []
        self._setup_ui()
        self._refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        # Persisted points change at most every 15 seconds; avoid repeatedly
        # decoding a full 24-hour range at paint-frame frequency.
        self._timer.start(1000)

    def _apply_engineering_settings(self, settings: EngineeringSettings) -> None:
        roi_count_changed = settings.roi_count != self._roi_count
        self._roi_count = settings.roi_count
        self._trend_point_mode = settings.trend_point_mode
        self._trend_downsampling_mode = settings.trend_downsampling_mode
        if hasattr(self, "stack"):
            if roi_count_changed:
                self._rebuild_roi_metric_tabs()
            self._refresh()

    def closeEvent(self, event) -> None:
        if self._unsubscribe_engineering is not None:
            self._unsubscribe_engineering()
            self._unsubscribe_engineering = None
        super().closeEvent(event)

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.tab_bar = _TrendTabBar()
        outer.addWidget(self.tab_bar)

        # thin amber rule below tab bar
        self._tab_rule = QFrame()
        self._tab_rule.setFrameShape(QFrame.HLine)
        self._tab_rule.setFixedHeight(2)
        self._tab_rule.setStyleSheet(f"background:{_AMBER};border:none;")
        outer.addWidget(self._tab_rule)

        self._selector = QWidget()
        self._selector.setFixedHeight(42)
        selector_lay = QHBoxLayout(self._selector)
        selector_lay.setContentsMargins(8, 3, 8, 3)
        self.study_combo = QComboBox()
        self.study_combo.currentIndexChanged.connect(lambda _index: self._refresh())
        selector_lay.addWidget(self.study_combo, stretch=2)
        self.range_combo = QComboBox()
        for label, seconds in (("5 мин", 300), ("15 мин", 900), ("30 мин", 1800),
                               ("1 ч", 3600), ("6 ч", 21600), ("24 ч", 86400)):
            self.range_combo.addItem(label, seconds)
        self.range_combo.currentIndexChanged.connect(lambda _index: self._refresh())
        selector_lay.addWidget(self.range_combo)
        self.time_scroll = QSlider(Qt.Horizontal)
        self.time_scroll.setRange(0, 1000)
        self.time_scroll.setValue(1000)
        self.time_scroll.valueChanged.connect(lambda _value: self._refresh())
        selector_lay.addWidget(self.time_scroll, stretch=3)
        outer.addWidget(self._selector)
        self._sync_studies()

        self.stack = QStackedWidget()
        self._regional_metrics = _regional_trend_metrics(self._roi_count)
        self._calculated_metrics = _GLOBAL_TREND_METRICS + self._regional_metrics
        self.tab_global   = _MetricChartsTab(_GLOBAL_TREND_METRICS)
        self.tab_regional = _MetricChartsTab(self._regional_metrics)
        self.tab_all      = _MetricChartsTab(self._calculated_metrics)
        self.stack.addWidget(self.tab_global)
        self.stack.addWidget(self.tab_regional)
        self.stack.addWidget(self.tab_all)
        outer.addWidget(self.stack, stretch=1)

        self.bottom = _BottomBar()
        outer.addWidget(self.bottom)

        self.tab_bar.tab_changed.connect(self.stack.setCurrentIndex)
        i18n.language_changed.connect(self.retranslate)

    def _rebuild_roi_metric_tabs(self) -> None:
        current_index = self.stack.currentIndex()
        old_regional, old_all = self.tab_regional, self.tab_all
        self._regional_metrics = _regional_trend_metrics(self._roi_count)
        self._calculated_metrics = _GLOBAL_TREND_METRICS + self._regional_metrics
        self.tab_regional = _MetricChartsTab(self._regional_metrics)
        self.tab_all = _MetricChartsTab(self._calculated_metrics)
        self.stack.removeWidget(old_regional)
        self.stack.removeWidget(old_all)
        old_regional.deleteLater()
        old_all.deleteLater()
        self.stack.insertWidget(1, self.tab_regional)
        self.stack.insertWidget(2, self.tab_all)
        self.stack.setCurrentIndex(current_index)

    def _refresh(self):
        waves, events = self._stored_view()
        idx = self.stack.currentIndex()
        if idx == 0:
            self.tab_global.refresh(waves)
        elif idx == 1:
            self.tab_regional.refresh(waves)
        else:
            self.tab_all.refresh(waves)
        for wave in (
            self.tab_global.wave,
            self.tab_regional.wave,
            self.tab_all.wave,
        ):
            wave.set_quality_intervals(waves.get("bad_intervals", ()))
            wave.set_event_markers(events, waves["time"])

    def _sync_studies(self):
        if self._study_repository is None:
            return
        selected = self.study_combo.currentData()
        studies = tuple(self._study_repository.list_all())
        ids = [study.id for study in studies]
        if ids == self._study_ids:
            return
        self._study_ids = ids
        self.study_combo.blockSignals(True)
        self.study_combo.clear()
        for study in studies:
            self.study_combo.addItem(
                f"{study.created_at_utc.astimezone().strftime('%d.%m.%Y %H:%M')} · "
                f"{study_status_text(study.status)}",
                str(study.id),
            )
        target = selected
        current = self._lifecycle.current_study if self._lifecycle is not None else None
        if current is not None and current.status in {StudyStatus.RUNNING, StudyStatus.PAUSED}:
            target = str(current.id)
        elif target is None and current is not None:
            target = str(current.id)
        index = self.study_combo.findData(target)
        self.study_combo.setCurrentIndex(max(0, index))
        self.study_combo.blockSignals(False)

    def _stored_view(self):
        self._sync_studies()
        empty = {
            "time": np.asarray([], dtype=float), "global": np.asarray([], dtype=float),
            "r": np.asarray([], dtype=float), "l": np.asarray([], dtype=float),
            "rois": [np.asarray([], dtype=float) for _ in range(self._roi_count)],
            "r_absolute": np.asarray([], dtype=float),
            "l_absolute": np.asarray([], dtype=float),
            "axis_range": (0.0, float(self.range_combo.currentData() or 300)),
            "bad_intervals": (),
            "metrics": {
                code: np.asarray([], dtype=float)
                for _label, code, _unit in self._calculated_metrics
            },
            "cycles": {
                "global": np.asarray([], dtype=float),
                "r": np.asarray([], dtype=float),
                "l": np.asarray([], dtype=float),
                "rois": [
                    np.asarray([], dtype=float) for _ in range(self._roi_count)
                ],
            },
        }
        value = self.study_combo.currentData()
        if self._trend_service is None or value is None:
            return empty, ()
        study_id = UUID(value)
        window = int(self.range_combo.currentData() or 300)

        def marker_events(start: float, end: float):
            if self._event_repository is None:
                return ()
            return tuple(
                event for event in self._event_repository.list_for_study(study_id)
                if event.category is EventCategory.MARKER
                and start <= event.position_seconds <= end
            )

        aggregation_kind = self._trend_point_mode
        bounds = self._trend_service.position_bounds(
            study_id, aggregation_kind=aggregation_kind
        )
        if bounds is None:
            # A marker is available immediately, while the first persisted
            # trend aggregate appears only after its aggregation interval.
            return empty, marker_events(0.0, float(window))
        _first, last = bounds
        total = max(0.0, last - window)
        start = total * self.time_scroll.value() / 1000.0
        end = start + window
        persisted = self._trend_service.read_position(
            study_id, start, end, aggregation_kind=aggregation_kind
        ).points
        cycles = self._trend_service.read_position(
            study_id, start, end, aggregation_kind="breath_cycle"
        ).points
        baseline = self._trend_service.baseline(
            study_id, aggregation_kind=aggregation_kind
        )
        points = []
        for point in persisted:
            if points and point.position_seconds - points[-1].position_seconds > 22.5:
                points.append(None)
            points.append(point)
        def values(name):
            return np.asarray([
                (
                    getattr(point, name)
                    if point is not None
                    else np.nan
                )
                for point in points
            ], dtype=float)
        def calculated_values(code):
            result = []
            for point in points:
                if point is None:
                    result.append(np.nan)
                    continue
                value = point.metric_value(code)
                if value is None and code == "rr_bpm":
                    value = point.respiratory_rate_bpm
                result.append(np.nan if value is None else value)
            return np.asarray(result, dtype=float)
        roi_count = max((len(point.roi_values) for point in persisted), default=8)
        times = np.asarray([
                point.position_seconds if point is not None else (
                    points[index - 1].position_seconds + 15.0
                )
                for index, point in enumerate(points)
            ], dtype=float)
        global_absolute = values("global_value")
        right_absolute = values("right_value")
        left_absolute = values("left_value")
        roi_absolute = [np.asarray([
                (
                    point.roi_values[index]
                    if point is not None
                    and index < len(point.roi_values)
                    else np.nan
                )
                for point in points
            ], dtype=float) for index in range(roi_count)]

        def cycle_values(name):
            return np.asarray([
                getattr(point, name)
                for point in cycles
            ], dtype=float)

        cycle_roi_count = max((len(point.roi_values) for point in cycles), default=roi_count)
        cycle_rois = [np.asarray([
            (
                point.roi_values[index]
                if index < len(point.roi_values)
                else np.nan
            )
            for point in cycles
        ], dtype=float) for index in range(cycle_roi_count)]
        waves = {
            "time": times,
            "global": _relative_percent(
                global_absolute, baseline.global_value if baseline else None
            ),
            "r": _relative_percent(
                right_absolute, baseline.right_value if baseline else None
            ),
            "l": _relative_percent(
                left_absolute, baseline.left_value if baseline else None
            ),
            "rois": [
                _relative_percent(
                    values_,
                    baseline.roi_values[index]
                    if baseline and index < len(baseline.roi_values) else None,
                )
                for index, values_ in enumerate(roi_absolute)
            ],
            "r_absolute": right_absolute,
            "l_absolute": left_absolute,
            "axis_range": (start, end),
            "bad_intervals": (),
            "metrics": {
                code: calculated_values(code)
                for _label, code, _unit in self._calculated_metrics
            },
            "cycles": {
                "global": _relative_percent(
                    cycle_values("global_value"),
                    baseline.global_value if baseline else None,
                ),
                "r": _relative_percent(
                    cycle_values("right_value"),
                    baseline.right_value if baseline else None,
                ),
                "l": _relative_percent(
                    cycle_values("left_value"),
                    baseline.left_value if baseline else None,
                ),
                "rois": [
                    _relative_percent(
                        values_,
                        baseline.roi_values[index]
                        if baseline and index < len(baseline.roi_values) else None,
                    )
                    for index, values_ in enumerate(cycle_rois)
                ],
            },
        }
        factor = _trend_median_factor(self._trend_downsampling_mode, window)
        waves["time"] = _last_reduce(waves["time"], factor)
        waves["metrics"] = {
            code: _median_reduce(values_, factor)
            for code, values_ in waves["metrics"].items()
        }
        waves["downsampling_factor"] = factor
        return waves, marker_events(start, end)

    def retranslate(self):
        self.tab_bar.retranslate()
        self.bottom.retranslate()
        if hasattr(self.tab_regional, "retranslate"):
            self.tab_regional.retranslate()
        self._study_ids = []
        self._sync_studies()
