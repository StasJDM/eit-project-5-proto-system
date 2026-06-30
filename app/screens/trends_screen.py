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

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QBrush

from ..mock_data import BreathingSimulator, DISPLAY_WINDOW_SEC, DISPLAY_SAMPLES, BREATHS_IN_WINDOW
from ..waveform_draw import draw_filled_waveform
from ..styles import (
    C, AERATION_COLOR_T, AERATION_COLOR_R, AERATION_COLOR_L,
    AERATION_ROI_R, AERATION_ROI_L,
    configure_event_marker_btn, EVENT_MARKER_BTN_HEIGHT, EVENT_MARKER_BTN_MIN_WIDTH,
    TAB_BAR_FONT, TAB_BAR_SUB_FONT, FONT_BTN, FONT_LABEL, FONT_SMALL, FONT_VALUE,
)
from ..i18n import t, i18n


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


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _static_bars(
    seed: int = 0,
    base: float = 55.0,
    noise: float = 10.0,
    n: int = BREATHS_IN_WINDOW,
) -> np.ndarray:
    """Фиксированные значения столбцов (детерминированный seed)."""
    rng = np.random.default_rng(seed)
    vals = base + np.sin(np.linspace(0.3, 3.0, n)) * noise + rng.normal(0, noise * 0.2, n)
    return np.clip(vals, 5.0, 100.0).astype(float)


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
        self._data = _static_bars(seed=seed)
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
        """Гистограммы статичны — не перерисовываем при тике таймера."""
        pass


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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_data(self, data_list: list[np.ndarray]):
        self._data = list(data_list)
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
                lo, hi = float(data.min()), float(data.max())
                if hi - lo < 1e-9:
                    hi = lo + 1.0

                mid_y = ch_top + ch_h / 2
                p.setPen(QPen(QColor(C["border"]), 1, Qt.DotLine))
                p.drawLine(ML, int(mid_y), ML + pw, int(mid_y))

                xs, ys = [], []
                pad = 3 if is_compact else 4
                baseline = ch_top + ch_h - pad
                for i in range(n):
                    x = ML + (i / (n - 1)) * pw
                    y = ch_top + pad + (1.0 - (data[i] - lo) / (hi - lo)) * (ch_h - 2 * pad)
                    xs.append(x)
                    ys.append(y)

                draw_filled_waveform(p, xs, ys, QColor(color), baseline)

            ch_top += ch_h


class _TrendTable(QWidget):
    """Grid table with static mock historical data."""

    N_COLS, N_ROWS = 6, 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(100, 50)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        rng = np.random.default_rng(42)
        self._vals = rng.integers(40, 80, (self.N_ROWS, self.N_COLS)).tolist()

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
        box = QLabel("55")
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

    def refresh(self):
        pass


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

    def __init__(self, sim: BreathingSimulator, parent=None):
        super().__init__(parent)
        self._sim = sim
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


class _RegionalPage(QWidget):
    """One side (R or L) for the regional tab."""

    def __init__(self, channels: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        self.left  = _LeftPanel(channels, channel_weights=_REGIONAL_ROW_WEIGHTS)
        self.right = _RightPanel(channels, row_weights=_REGIONAL_ROW_WEIGHTS)
        lay.addWidget(self.left,  stretch=_LEFT_STRETCH)
        lay.addWidget(_vsep())
        lay.addWidget(self.right, stretch=_RIGHT_STRETCH)

    def refresh(self, wave_list: list[np.ndarray]):
        self.left.wave.set_data(wave_list)


class _RegionalTab(QWidget):
    """Tab 2: Regional aeration trend — R / L toggle."""

    def __init__(self, sim: BreathingSimulator, parent=None):
        super().__init__(parent)
        self._sim  = sim
        self._side = "R"

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
        self.page_r = _RegionalPage(_RIGHT_CH)
        self.page_l = _RegionalPage(_LEFT_CH)
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
        r_data = [rois[0], rois[0], rois[1], rois[2], rois[3]]   # R + ROI_1..4
        l_data = [rois[4], rois[4], rois[5], rois[6], rois[7]]   # L + ROI_5..8
        self.page_r.refresh(r_data)
        self.page_l.refresh(l_data)

    def retranslate(self):
        self.btn_r.setText(t("trends_right_short"))
        self.btn_l.setText(t("trends_left_short"))


class _AllTrendsTab(QWidget):
    """Tab 3: Global + Regional combined long-term view."""

    def __init__(self, sim: BreathingSimulator, parent=None):
        super().__init__(parent)
        self._sim = sim

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
        for lf, rf in [(0.30, 0.35), (0.55, 0.60), (0.75, 0.80)]:
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
            b2 = QLabel("55")
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
    """Trends screen with three tabs and live mock data refresh."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sim = BreathingSimulator()
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

        self.stack = QStackedWidget()
        self.tab_global   = _GlobalTab(self._sim)
        self.tab_regional = _RegionalTab(self._sim)
        self.tab_all      = _AllTrendsTab(self._sim)
        self.stack.addWidget(self.tab_global)
        self.stack.addWidget(self.tab_regional)
        self.stack.addWidget(self.tab_all)
        outer.addWidget(self.stack, stretch=1)

        self.bottom = _BottomBar()
        outer.addWidget(self.bottom)

        self.tab_bar.tab_changed.connect(self.stack.setCurrentIndex)
        i18n.language_changed.connect(self.retranslate)

    def _refresh(self):
        self._sim.step()
        waves = self._sim.get_waveforms()
        idx = self.stack.currentIndex()
        if idx == 0:
            self.tab_global.refresh(waves)
        elif idx == 1:
            self.tab_regional.refresh(waves)
        else:
            self.tab_all.refresh(waves)

    def retranslate(self):
        self.tab_bar.retranslate()
        self.bottom.retranslate()
        if hasattr(self.tab_regional, "retranslate"):
            self.tab_regional.retranslate()
