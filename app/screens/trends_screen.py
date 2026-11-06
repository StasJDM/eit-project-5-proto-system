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

from datetime import timedelta, timezone
from uuid import UUID

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QSizePolicy, QComboBox, QSlider,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QBrush

from ..application import EventMarkerService, MonitoringData, TrendService
from ..domain import DataQuality, EventCategory, StudyStatus
from ..application.monitoring import DISPLAY_WINDOW_SEC, DISPLAY_SAMPLES, BREATHS_IN_WINDOW
from ..waveform_draw import draw_filled_waveform
from ..styles import (
    C, AERATION_COLOR_T, AERATION_COLOR_R, AERATION_COLOR_L,
    AERATION_ROI_R, AERATION_ROI_L,
    configure_event_marker_btn, EVENT_MARKER_BTN_HEIGHT, EVENT_MARKER_BTN_MIN_WIDTH,
    TAB_BAR_FONT, TAB_BAR_SUB_FONT, FONT_BTN, FONT_LABEL, FONT_SMALL, FONT_VALUE,
)
from ..i18n import t, i18n
from ..ui_text import study_status_text


# ── Typography (12″ display) — из styles + локальные акценты ─────────────────
_TREND_LABEL = FONT_LABEL
_TREND_VALUE = FONT_VALUE
_TREND_DIM   = FONT_SMALL
_TREND_CH_PT = 16
_TREND_AXIS_PT = 14
_TREND_TABLE_PT = FONT_SMALL
_AMBER    = "#f9a825"
_AMBER_DK = "#3a2e00"
_CYAN     = "#00bcd4"
_CYAN_DIM = "#004d5a"


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
    """10-bar trend chart drawn with QPainter."""

    _Y_MAX = 100.0

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

        # ── Y-axis grid lines and labels (0 / 50 / 100 %) ───────────────────
        for frac, lbl in ((0.0, "0"), (0.5, "50"), (1.0, "100")):
            gy = int(mt + (1.0 - frac) * ph)
            p.setPen(QPen(QColor(C["border"]), 1, Qt.DotLine))
            p.drawLine(ml, gy, ml + pw, gy)
            p.setPen(QPen(QColor(C["text_lo"])))
            p.drawText(0, gy + 3, lbl)

        # ── Bars ─────────────────────────────────────────────────────────────
        bw = pw / n
        gap = max(1.0, bw * 0.18)
        max_v = self._Y_MAX

        for i, v in enumerate(self._data):
            x = ml + i * bw + gap / 2
            bar_w = bw - gap
            bh = max(1.0, v / max_v * ph)
            y = mt + ph - bh
            clr = QColor(_CYAN) if i == n - 1 else QColor(_CYAN_DIM)
            p.fillRect(int(x), int(y), max(1, int(bar_w)), int(bh), clr)
            p.setPen(QPen(QColor(_CYAN), 1))
            p.drawLine(int(x), int(y), int(x + bar_w), int(y))

        # ── X-axis labels (breath index 1..N) ────────────────────────────────
        p.setPen(QPen(QColor(C["text_lo"])))
        for i in range(n):
            cx = int(ml + i * bw + bw / 2 - 3)
            p.drawText(cx, h - 2, str(i + 1))

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
        self.lbl_pct.setFixedWidth(56)
        self.lbl_pct.setAlignment(Qt.AlignCenter)
        pct_font = _TREND_VALUE - 4 if compact else _TREND_VALUE
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
        self._markers: tuple[float, ...] = ()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_data(self, data_list: list[np.ndarray]):
        self._data = list(data_list)
        self.update()

    def set_event_markers(self, events, time_values):
        times = np.asarray(time_values, dtype=float)
        if times.size == 1:
            end = float(times[0]) + 0.5
            self._markers = tuple(
                1.0 for event in events if 0.0 <= float(event.position_seconds) <= end
            )
        elif times.size < 2 or times[-1] <= times[0]:
            self._markers = ()
        else:
            start, end = float(times[0]), float(times[-1])
            span = end - start
            self._markers = tuple(
                min(1.0, (float(event.position_seconds) - start) / span)
                for event in events
                if start <= float(event.position_seconds) <= end + 0.5
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

        ML, MR, MT, MB = 58, 4, 16, 20
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

        # time axis: 0 … 60 с
        for t_sec, lbl in ((0, "0с"), (15, "15с"), (30, "30с"), (45, "45с"), (60, "60с")):
            tx = int(ML + (t_sec / DISPLAY_WINDOW_SEC) * pw)
            p.setPen(QPen(QColor(C["border"]), 1))
            p.drawLine(tx, MT + int(tot_h), tx, MT + int(tot_h) + 3)
            p.setPen(QPen(QColor(C["text_lo"])))
            offset = -10 if t_sec == DISPLAY_WINDOW_SEC else (-4 if t_sec > 0 else 0)
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
                for i in range(n + 1):
                    value = data[i] if i < n else np.nan
                    if np.isfinite(value):
                        segment_x.append(ML + (i / (n - 1)) * pw)
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
    """Grid table with static mock historical data."""

    N_COLS, N_ROWS = 6, 4

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

            p.setPen(QPen(QColor(C["border"]), 1))
            p.setBrush(QBrush(QColor(C[color_key])))
            p.drawEllipse(ex, top, lw, lh)

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


def _npct_col() -> QWidget:
    """Column of 3 N,% label+box pairs."""
    col = QWidget()
    lay = QVBoxLayout(col)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lay.addStretch()
    for _ in range(3):
        row = QWidget()
        r = QHBoxLayout(row)
        r.setContentsMargins(0, 0, 0, 0)
        r.setSpacing(4)
        lbl = QLabel("N,%")
        lbl.setStyleSheet(
            f"color:{C['text_dim']};font-size:{_TREND_VALUE}px;background:transparent;"
        )
        box = QLabel("—")
        box.setFixedSize(52, 28)
        box.setAlignment(Qt.AlignCenter)
        box.setStyleSheet(
            f"background:{C['bg_card']};border:1px solid {C['border']};"
            f"color:{C['text']};font-size:{_TREND_VALUE}px;"
        )
        r.addWidget(lbl)
        r.addWidget(box)
        lay.addWidget(row)
    lay.addStretch()
    return col


def _table_block() -> QWidget:
    """Таблица label + grid."""
    col = QWidget()
    lay = QVBoxLayout(col)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lbl = QLabel(t("trends_table"))
    lbl.setStyleSheet(
        f"color:{C['text_dim']};font-size:{_TREND_LABEL}px;background:transparent;"
    )
    tbl = _TrendTable()
    lay.addWidget(lbl)
    lay.addWidget(tbl, stretch=1)
    return col


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
        b_lay.addWidget(_table_block(), stretch=1)
        b_lay.addWidget(_npct_col())
        lay.addWidget(bottom, stretch=1)


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
        self.left.wave.set_data([waves["global"]])
        self.right.refresh([waves["global"]])


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

    def refresh(self, wave_list: list[np.ndarray]):
        self.left.wave.set_data(wave_list)
        self.right.refresh(wave_list)


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
        self.page_r.refresh(r_data)
        self.page_l.refresh(l_data)

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

        u_lay.addWidget(self._param_section("trends_global_label", AERATION_COLOR_T), stretch=1)
        u_lay.addWidget(_vsep())
        u_lay.addWidget(self._param_section("trends_reg_label",    AERATION_COLOR_R), stretch=1)
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

        u_lay.addWidget(_table_block(), stretch=2)
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
        hrs = QLabel(t("trends_time_hours"))
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

        time_lbl = QLabel(t("trends_time_min"))
        time_lbl.setAlignment(Qt.AlignCenter)
        time_lbl.setStyleSheet(
            f"color:{C['text_lo']};font-size:{_TREND_DIM}px;background:transparent;"
        )
        l_lay.addWidget(time_lbl)

        outer.addWidget(lower, stretch=1)

    def _param_section(self, title_key: str, color: str) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(4)
        lbl = QLabel(t(title_key))
        lbl.setStyleSheet(
            f"color:{color};font-size:{_TREND_LABEL}px;font-weight:bold;background:transparent;"
        )
        lay.addWidget(lbl)
        for _ in range(2):
            row = QWidget()
            r = QHBoxLayout(row)
            r.setContentsMargins(0, 0, 0, 0)
            r.setSpacing(4)
            l2 = QLabel("N,%")
            l2.setStyleSheet(
                f"color:{C['text_dim']};font-size:{_TREND_VALUE}px;background:transparent;"
            )
            b2 = QLabel("—")
            b2.setFixedSize(48, 26)
            b2.setAlignment(Qt.AlignCenter)
            b2.setStyleSheet(
                f"background:{C['bg_card']};border:1px solid {C['border']};"
                f"color:{C['text']};font-size:{_TREND_VALUE}px;"
            )
            r.addWidget(l2)
            r.addWidget(b2)
            lay.addWidget(row)
        lay.addStretch()
        return box

    def refresh(self, waves: dict):
        self.long_wave.set_data([waves["global"]])
        self.main_bar.refresh(np.asarray(waves["global"], dtype=float))
        right = np.asarray(waves.get("r", []), dtype=float)
        left = np.asarray(waves.get("l", []), dtype=float)
        valid = np.flatnonzero(np.isfinite(right) & np.isfinite(left))
        if valid.size:
            index = int(valid[-1])
            total = max(abs(float(right[index])) + abs(float(left[index])), 1e-9)
            for icon in self.lung_icons:
                icon.set_fill(
                    abs(float(left[index])) / total,
                    abs(float(right[index])) / total,
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
    ):
        super().__init__(parent)
        self._monitoring = monitoring
        self._marker_service = marker_service
        self._trend_service = trend_service
        self._study_repository = study_repository
        self._event_repository = event_repository
        self._lifecycle = lifecycle
        self._study_ids: list[UUID] = []
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(200)   # 5 fps — enough for trend visualisation

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.tab_bar = _TrendTabBar()
        outer.addWidget(self.tab_bar)

        # thin amber rule below tab bar
        rule = QFrame()
        rule.setFrameShape(QFrame.HLine)
        rule.setFixedHeight(2)
        rule.setStyleSheet(f"background:{_AMBER};border:none;")
        outer.addWidget(rule)

        selector = QWidget()
        selector.setFixedHeight(42)
        selector_lay = QHBoxLayout(selector)
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
        outer.addWidget(selector)
        self._sync_studies()

        self.stack = QStackedWidget()
        self.tab_global   = _GlobalTab()
        self.tab_regional = _RegionalTab()
        self.tab_all      = _AllTrendsTab()
        self.stack.addWidget(self.tab_global)
        self.stack.addWidget(self.tab_regional)
        self.stack.addWidget(self.tab_all)
        outer.addWidget(self.stack, stretch=1)

        self.bottom = _BottomBar()
        outer.addWidget(self.bottom)

        self.tab_bar.tab_changed.connect(self.stack.setCurrentIndex)
        i18n.language_changed.connect(self.retranslate)

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
            self.tab_global.left.wave,
            self.tab_regional.page_r.left.wave,
            self.tab_regional.page_l.left.wave,
            self.tab_all.long_wave,
        ):
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
            "rois": [np.asarray([], dtype=float) for _ in range(8)],
        }
        value = self.study_combo.currentData()
        if self._trend_service is None or value is None:
            return empty, ()
        study_id = UUID(value)
        bounds = self._trend_service.bounds(study_id)
        if bounds is None:
            return empty, ()
        first, last = bounds
        window = int(self.range_combo.currentData() or 300)
        total = max(0.0, (last - first).total_seconds() - window)
        end = last if total <= 0 else first + timedelta(
            seconds=window + total * self.time_scroll.value() / 1000.0
        )
        start = end - timedelta(seconds=window)
        persisted = self._trend_service.read(study_id, start, end).points
        points = []
        for point in persisted:
            if points and point.position_seconds - points[-1].position_seconds > 22.5:
                points.append(None)
            points.append(point)
        def values(name):
            return np.asarray([
                (
                    getattr(point, name)
                    if point is not None and point.quality is DataQuality.VALID
                    else np.nan
                )
                for point in points
            ], dtype=float)
        roi_count = max((len(point.roi_values) for point in persisted), default=8)
        waves = {
            "time": np.asarray([
                point.position_seconds if point is not None else (
                    points[index - 1].position_seconds + 15.0
                )
                for index, point in enumerate(points)
            ], dtype=float),
            "global": values("global_value"),
            "r": values("right_value"),
            "l": values("left_value"),
            "rois": [np.asarray([
                (
                    point.roi_values[index]
                    if point is not None
                    and index < len(point.roi_values)
                    and point.quality is DataQuality.VALID
                    else np.nan
                )
                for point in points
            ], dtype=float) for index in range(roi_count)],
        }
        events = ()
        if self._event_repository is not None:
            events = tuple(
                event for event in self._event_repository.search(
                    study_id, start_utc=start, end_utc=end + timedelta(seconds=1)
                ) if event.category is EventCategory.MARKER
            )
        return waves, events

    def retranslate(self):
        self.tab_bar.retranslate()
        self.bottom.retranslate()
        if hasattr(self.tab_regional, "retranslate"):
            self.tab_regional.retranslate()
        self._study_ids = []
        self._sync_studies()
