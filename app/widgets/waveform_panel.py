"""9-channel real-time waveform display.

Supports runtime language switching via i18n.language_changed.
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy
)
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from ..waveform_draw import draw_filled_waveform
from ..application.monitoring import DISPLAY_SAMPLES
from ..styles import (
    C, WAVE_COLORS, AERATION_COLOR_T, AERATION_COLOR_R, AERATION_COLOR_L,
    AERATION_ROI_R, AERATION_ROI_L, SECTION_COLORS,
    configure_event_marker_btn, EVENT_MARKER_BTN_HEIGHT, FONT_SMALL,
    FONT_MEDICAL_VALUE,
)
from ..i18n import t, i18n


# ── Single waveform canvas ───────────────────────────────────────────────────

class _WaveCanvas(QWidget):
    """Custom-painted rolling waveform line."""

    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._data  = np.zeros(DISPLAY_SAMPLES)
        self._markers: tuple[tuple[float, str], ...] = ()
        self._color = QColor(color)
        self._bg    = QColor(C["bg_wave"])
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_data(self, arr: np.ndarray):
        self._data = arr
        self.update()

    def set_markers(self, markers: tuple[tuple[float, str], ...]):
        self._markers = markers
        self.update()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, self._bg)

        data = self._data
        n = len(data)
        if n < 2:
            return

        mx, my = 2, 5
        pw = w - 2 * mx
        ph = h - 2 * my

        lo, hi = float(data.min()), float(data.max())
        if hi - lo < 1e-9:
            hi = lo + 1.0

        z_y = my + (1.0 - (0.0 - lo) / (hi - lo)) * ph
        if my < z_y < my + ph:
            painter.setPen(QPen(QColor(C["border"]), 1, Qt.DotLine))
            painter.drawLine(mx, int(z_y), mx + pw, int(z_y))

        xs, ys = [], []
        for i in range(n):
            x = mx + (i / (n - 1)) * pw
            y = my + (1.0 - (data[i] - lo) / (hi - lo)) * ph
            xs.append(x)
            ys.append(y)

        draw_filled_waveform(painter, xs, ys, self._color, my + ph)
        painter.setPen(QPen(QColor(C["warn"]), 2, Qt.DashLine))
        for position, _label in self._markers:
            x = mx + max(0.0, min(1.0, position)) * pw
            painter.drawLine(int(x), my, int(x), my + ph)


def _format_monitoring_time(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class _MonitoringMomentBar(QWidget):
    """Horizontal time strip ending at the latest monitoring sample."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_seconds: float | None = None
        self._current_seconds: float | None = None
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        i18n.language_changed.connect(self.update)

    @property
    def start_seconds(self) -> float | None:
        return self._start_seconds

    @property
    def current_seconds(self) -> float | None:
        return self._current_seconds

    def set_time_values(self, values) -> None:
        times = np.asarray(values, dtype=float).reshape(-1)
        finite = times[np.isfinite(times)]
        if finite.size:
            self._start_seconds = float(finite[0])
            self._current_seconds = float(finite[-1])
        else:
            self._start_seconds = None
            self._current_seconds = None
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(C["bg_wave"]))

        left = 10.0
        right = max(left + 1.0, self.width() - 10.0)
        track = QRectF(left, 5.0, right - left, 7.0)
        painter.setPen(QPen(QColor(C["border_light"]), 1))
        painter.setBrush(QBrush(QColor(C["bg_card"])))
        painter.drawRoundedRect(track, 3.5, 3.5)

        if self._current_seconds is not None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(C["blue"])))
            painter.drawRoundedRect(track, 3.5, 3.5)
            painter.setPen(QPen(QColor(C["text"]), 2))
            painter.setBrush(QBrush(QColor(C["blue_light"])))
            painter.drawEllipse(QRectF(right - 5.0, 1.5, 10.0, 14.0))

        painter.setPen(QPen(QColor(C["text_dim"]), 1))
        start_text = (
            _format_monitoring_time(self._start_seconds)
            if self._start_seconds is not None else "—"
        )
        current_text = (
            _format_monitoring_time(self._current_seconds)
            if self._current_seconds is not None else "—"
        )
        text_top = 16.0
        half = self.width() / 2.0
        painter.drawText(
            QRectF(left, text_top, half - left, 18.0),
            Qt.AlignLeft | Qt.AlignVCenter,
            start_text,
        )
        painter.setPen(QPen(QColor(C["text"]), 1))
        painter.drawText(
            QRectF(half, text_top, right - half, 18.0),
            Qt.AlignRight | Qt.AlignVCenter,
            f"{t('wave_monitoring_moment')}: {current_text}",
        )


# ── Single labelled waveform row ─────────────────────────────────────────────

_LBL_ROI   = 22   # было 11 px
_LBL_DIM   = 18   # было 9 px  (ЧД, N,%)
_LBL_UNIT  = 16   # было 8 px  (вд/мин)
_HDR_FONT  = 22   # было 11 px  (заголовки секций)

# Доли вертикального пространства на главном экране
# Глобальная ≈ 60 % от прежней доли (было 4:1 → стало ~7:18 ≈ 28 % полосы)
_MAIN_GLOBAL_STRETCH   = 7
_MAIN_REGIONAL_STRETCH = 18
_MAIN_AGG_STRETCH      = 4    # средний график Σ R / Σ L (было 3)
_MAIN_ROI_STRETCH      = 2    # малые ROI (было 1)

_ROW_SIZES = {
    "normal":  {"height": 68, "label_w": 96, "lbl_font": 22, "pct_w": 96, "pct_font": FONT_MEDICAL_VALUE},
    "large":   {"height": 76, "label_w": 96, "lbl_font": 20, "pct_w": 96, "pct_font": FONT_MEDICAL_VALUE},
    "medium":  {"height": 58, "label_w": 72, "lbl_font": 18, "pct_w": 84, "pct_font": 28},
    "compact": {"height": 48, "label_w": 68, "lbl_font": 15, "pct_w": 78, "pct_font": 24},
}


class _WaveRow(QWidget):
    def __init__(
        self,
        label: str,
        color: str,
        show_rr: bool = False,
        expand: bool = False,
        stack_metrics: bool = False,
        size: str = "normal",
        parent=None,
    ):
        super().__init__(parent)
        spec = _ROW_SIZES.get(size, _ROW_SIZES["normal"])
        if expand:
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            self.setFixedHeight(spec["height"])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 1, 4, 1)
        lay.setSpacing(6)

        self._color = color
        self.rr_box = None
        self.metrics_stack = None
        metric_scale = 2 if stack_metrics else 1
        metric_width = spec["pct_w"] * metric_scale
        metric_height = spec["height"] * metric_scale

        lbl = QLabel(label)
        lbl.setFixedWidth(spec["label_w"])
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl.setStyleSheet(
            f"color: {color}; font-size: {spec['lbl_font']}px; font-weight: bold; background: transparent;"
        )
        lay.addWidget(lbl)

        self.canvas = _WaveCanvas(color)
        self.canvas.setMinimumHeight(28 if size == "compact" else 36)
        lay.addWidget(self.canvas, stretch=1)

        if show_rr:
            rr_box = QWidget()
            self.rr_box = rr_box
            rr_box.setFixedWidth(metric_width if stack_metrics else 100)
            rr_box.setFixedHeight(metric_height)
            rr_lay = QVBoxLayout(rr_box)
            rr_lay.setContentsMargins(2, 0, 2, 0)
            rr_lay.setSpacing(0)
            rr_lay.setAlignment(Qt.AlignVCenter)
            self._lbl_rr_title = QLabel(t("wave_rr_short"))
            self._lbl_rr_title.setAlignment(Qt.AlignCenter)
            self._lbl_rr_title.setStyleSheet(
                f"color: {C['text_dim']}; font-size: {_LBL_DIM * metric_scale}px; background: transparent;"
            )
            self.lbl_rr_val = QLabel("15")
            self.lbl_rr_val.setAlignment(Qt.AlignCenter)
            self.lbl_rr_val.setStyleSheet(
                f"color: {C['text']}; font-size: {spec['pct_font'] * metric_scale}px; font-weight: bold; background: transparent;"
            )
            self.lbl_rr_unit = QLabel(t("wave_rr_unit"))
            self.lbl_rr_unit.setAlignment(Qt.AlignCenter)
            self.lbl_rr_unit.setStyleSheet(
                f"color: {C['text_dim']}; font-size: {_LBL_UNIT * metric_scale}px; background: transparent;"
            )
            rr_lay.addWidget(self._lbl_rr_title)
            rr_lay.addWidget(self.lbl_rr_val)
            rr_lay.addWidget(self.lbl_rr_unit)
            if not stack_metrics:
                lay.addWidget(rr_box, 0, Qt.AlignVCenter)
        else:
            self._lbl_rr_title = None
            self.lbl_rr_val  = None
            self.lbl_rr_unit = None

        pct_font = spec["pct_font"]
        self._metric_value_font = pct_font * metric_scale
        pct_box = QWidget()
        self.pct_box = pct_box
        pct_box.setFixedWidth(metric_width)
        pct_box.setFixedHeight(metric_height)
        pct_lay = QVBoxLayout(pct_box)
        pct_lay.setContentsMargins(2, 0, 2, 0)
        pct_lay.setSpacing(0)
        pct_lay.setAlignment(Qt.AlignVCenter)
        lbl_pct_title = QLabel("N,%")
        lbl_pct_title.setAlignment(Qt.AlignCenter)
        lbl_pct_title.setStyleSheet(
            f"color:{C['text_dim']};font-size:{(_LBL_DIM if size != 'compact' else 14) * metric_scale}px;background:transparent;"
        )
        self.lbl_pct = QLabel("0.0")
        self.lbl_pct.setAlignment(Qt.AlignCenter)
        self.lbl_pct.setStyleSheet(
            f"color:{C['text']};font-size:{pct_font * metric_scale}px;font-weight:bold;background:transparent;"
        )
        pct_lay.addWidget(lbl_pct_title)
        pct_lay.addWidget(self.lbl_pct)
        if not stack_metrics:
            lay.addWidget(pct_box, 0, Qt.AlignVCenter)

        tr_box = QWidget()
        self.trend_box = tr_box
        tr_box.setFixedWidth(metric_width)
        tr_box.setFixedHeight(metric_height)
        tr_lay = QVBoxLayout(tr_box)
        tr_lay.setContentsMargins(2, 0, 2, 0)
        tr_lay.setSpacing(0)
        tr_lay.setAlignment(Qt.AlignVCenter)
        self._lbl_trend_title = QLabel(t("wave_trend"))
        self._lbl_trend_title.setAlignment(Qt.AlignCenter)
        dim = (_LBL_DIM if size != "compact" else 14) * metric_scale
        self._lbl_trend_title.setStyleSheet(
            f"color:{C['text_dim']};font-size:{dim}px;background:transparent;"
        )
        self.lbl_trend = QLabel("▲0.0")
        self.lbl_trend.setFixedHeight((pct_font + 6) * metric_scale)
        self.lbl_trend.setAlignment(Qt.AlignCenter)
        self._apply_trend_style(0.0)
        tr_lay.addWidget(self._lbl_trend_title)
        tr_lay.addWidget(self.lbl_trend)
        if stack_metrics:
            metrics_stack = QWidget()
            self.metrics_stack = metrics_stack
            metrics_stack.setFixedWidth(metric_width)
            metrics_stack.setFixedHeight(metric_height * 3 + 16)
            metrics_lay = QVBoxLayout(metrics_stack)
            metrics_lay.setContentsMargins(0, 0, 0, 0)
            metrics_lay.setSpacing(8)
            metrics_lay.addWidget(self.rr_box)
            metrics_lay.addWidget(pct_box)
            metrics_lay.addWidget(tr_box)
            lay.addWidget(metrics_stack, 0, Qt.AlignVCenter)
        else:
            lay.addWidget(tr_box, 0, Qt.AlignVCenter)

        i18n.language_changed.connect(self.retranslate)

    def update_data(self, arr: np.ndarray):
        self.canvas.set_data(arr)

    def update_pct(self, value: float | None):
        self.lbl_pct.setText("—" if value is None else f"{value:.1f}")

    def update_trend(self, value: float | None):
        if value is None:
            self.lbl_trend.setText("—")
            self.lbl_trend.setStyleSheet(f"""
                background-color:{C['bg_card']};color:{C['text_dim']};
                border:1px solid {C['border']};border-radius:3px;
                font-size:{self._metric_value_font}px;
                font-weight:bold;
            """)
            return
        arrow = "▲" if value >= 0 else "▼"
        self.lbl_trend.setText(f"{arrow}{abs(value):.1f}")
        self._apply_trend_style(value)

    def _apply_trend_style(self, value: float):
        col = C["ok_hover"] if value >= 0 else C["alarm"]
        self.lbl_trend.setStyleSheet(f"""
            background-color:{C['bg_card']};
            color:{col};
            border:1px solid {C['border']};
            border-radius:3px;
            font-size:{self._metric_value_font}px;
            font-weight:bold;
        """)

    def update_rr(self, rr: float | None):
        if self.lbl_rr_val:
            self.lbl_rr_val.setText("—" if rr is None else f"{rr:.0f}")

    def retranslate(self):
        if self._lbl_rr_title:
            self._lbl_rr_title.setText(t("wave_rr_short"))
        if self.lbl_rr_unit:
            self.lbl_rr_unit.setText(t("wave_rr_unit"))
        self._retranslate_trend_title()

    def _retranslate_trend_title(self):
        if hasattr(self, "_lbl_trend_title"):
            self._lbl_trend_title.setText(t("wave_trend"))


# ── Section header ────────────────────────────────────────────────────────────

class _SectionHeader(QWidget):

    def __init__(self, i18n_key: str, section: str, compact: bool = False, parent=None):
        super().__init__(parent)
        self._i18n_key = i18n_key
        self._color    = SECTION_COLORS.get(section, AERATION_COLOR_R)
        hdr_font = 18 if compact else _HDR_FONT
        self.setFixedHeight(36 if compact else 44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)

        self._tag = QLabel(f" {t(i18n_key)} ")
        self._tag.setStyleSheet(f"""
            background-color: {self._color};
            color: white;
            font-size: {hdr_font}px; font-weight: bold;
            border-radius: 3px; padding: 2px 8px;
        """)
        lay.addWidget(self._tag)
        lay.addStretch()

    def retranslate(self):
        self._tag.setText(f" {t(self._i18n_key)} ")


def _hsep():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{C['border']}; margin:0; max-height:1px;")
    return f


def _vsep():
    f = QFrame()
    f.setFrameShape(QFrame.VLine)
    f.setStyleSheet(f"color:{C['border']}; margin:0; max-width:1px;")
    return f


class _LungColumn:
    """Колонка регионарной аэрации: заголовок + суммарная + 4 ROI."""

    __slots__ = ("widget", "layout", "hdr", "agg", "rois", "section")

    def __init__(self, widget, layout, hdr, agg, rois, section):
        self.widget = widget
        self.layout = layout
        self.hdr = hdr
        self.agg = agg
        self.rois = rois
        self.section = section


# ── Regional aeration panel (10 graphs) ──────────────────────────────────────

class RegionalWaveformPanel(QWidget):
    """10 графиков: левая колонка L, правая колонка R."""

    regional_order = ("L", "R")

    def __init__(self, parent=None, *, roi_count: int = 8):
        super().__init__(parent)
        self._roi_count = roi_count
        self.setStyleSheet(f"background-color:{C['bg_wave']};")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(0)

        bands = roi_count // 2
        self._col_r = self._build_column("R", "wave_r_label", 0, bands)
        self._col_l = self._build_column("L", "wave_l_label", bands, bands)

        outer.addWidget(self._col_l.widget, stretch=1)
        outer.addWidget(_vsep())
        outer.addWidget(self._col_r.widget, stretch=1)

        i18n.language_changed.connect(self.retranslate)

    def _build_column(
        self, section: str, i18n_key: str, roi_start: int, band_count: int
    ) -> _LungColumn:
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(1)

        hdr = _SectionHeader(i18n_key, section, compact=True)
        lay.addWidget(hdr)

        agg_color = AERATION_COLOR_R if section == "R" else AERATION_COLOR_L
        agg = _WaveRow(f"Σ {section}", agg_color, size="medium", expand=True)
        lay.addWidget(agg, stretch=3)

        roi_colors = AERATION_ROI_R if section == "R" else AERATION_ROI_L
        rois: list[_WaveRow] = []
        for i in range(band_count):
            idx = roi_start + i
            row = _WaveRow(
                f"ROI_{idx + 1}", roi_colors[i % len(roi_colors)], size="compact"
            )
            lay.addWidget(row, stretch=1)
            rois.append(row)

        return _LungColumn(w, lay, hdr, agg, rois, section)

    def set_roi_count(self, roi_count: int) -> None:
        if roi_count == self._roi_count:
            return
        self._roi_count = roi_count
        bands = roi_count // 2
        self._rebuild_column_rois(self._col_r, 0, bands)
        self._rebuild_column_rois(self._col_l, bands, bands)

    def _rebuild_column_rois(
        self, column: _LungColumn, roi_start: int, band_count: int
    ) -> None:
        for row in column.rois:
            column.layout.removeWidget(row)
            row.deleteLater()
        colors = AERATION_ROI_R if column.section == "R" else AERATION_ROI_L
        column.rois = []
        for index in range(band_count):
            row = _WaveRow(
                f"ROI_{roi_start + index + 1}",
                colors[index % len(colors)],
                size="compact",
            )
            column.layout.addWidget(row, stretch=1)
            column.rois.append(row)

    def update_all(
        self,
        waves: dict,
        roi_pcts: list,
        r_pct: float,
        l_pct: float,
        trends: dict | None = None,
    ):
        rois = waves["rois"]
        bands = self._roi_count // 2
        r_agg = np.mean(rois[:bands], axis=0)
        l_agg = np.mean(rois[bands:], axis=0)

        self._col_r.agg.update_data(r_agg)
        self._col_r.agg.update_pct(r_pct)
        self._col_l.agg.update_data(l_agg)
        self._col_l.agg.update_pct(l_pct)
        for i, row in enumerate(self._col_r.rois):
            row.update_data(rois[i])
            row.update_pct(roi_pcts[i])
        for i, row in enumerate(self._col_l.rois):
            row.update_data(rois[i + bands])
            row.update_pct(roi_pcts[i + bands])

        if trends:
            self._col_r.agg.update_trend(trends.get("r", 0.0))
            self._col_l.agg.update_trend(trends.get("l", 0.0))
            roi_tr = trends.get("rois", [0.0] * 8)
            for i, row in enumerate(self._col_r.rois):
                row.update_trend(roi_tr[i] if i < len(roi_tr) else 0.0)
            for i, row in enumerate(self._col_l.rois):
                row.update_trend(
                    roi_tr[i + bands] if i + bands < len(roi_tr) else 0.0
                )

    def retranslate(self):
        self._col_r.hdr.retranslate()
        self._col_l.hdr.retranslate()
        for row in self._col_r.rois + self._col_l.rois:
            row.retranslate()

    def set_event_markers(self, events, time_values):
        markers = _relative_markers(events, time_values)
        for row in (
            self._col_r.agg, self._col_l.agg,
            *self._col_r.rois, *self._col_l.rois,
        ):
            row.canvas.set_markers(markers)


# ── Main waveform panel ───────────────────────────────────────────────────────

class WaveformPanel(QWidget):
    """9-channel display: global + left column + right column."""

    regional_order = ("L", "R")

    def __init__(
        self,
        show_global: bool = True,
        show_regional: bool = True,
        show_event_button: bool = True,
        expand_global: bool = False,
        show_velocity: bool = False,
        roi_count: int = 8,
        bottom_left_widget: QWidget | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._show_global = show_global
        self._show_regional = show_regional
        self._roi_count = roi_count
        self._trends_visible = True
        self._regional_column_layouts: dict[str, QVBoxLayout] = {}
        # Главный экран: 9 каналов в ~740 px — компактные ROI + растяжение Σ LI.
        self._dense = show_global and show_regional and not expand_global
        self.setStyleSheet(f"background-color:{C['bg_wave']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(0)

        self._hdr_t = None
        self.row_global = None
        self.row_velocity = None
        self.row_r_agg = None
        self.row_l_agg = None
        self._hdr_r = None
        self._hdr_l = None
        self._regional_widget = None
        self.rows_r: list[_WaveRow] = []
        self.rows_l: list[_WaveRow] = []

        if show_global:
            self._hdr_t = _SectionHeader(
                "wave_t_label", "T", compact=self._dense,
            )
            outer.addWidget(self._hdr_t)
            self.row_global = _WaveRow(
                "Σ LI", AERATION_COLOR_T, show_rr=True,
                expand=expand_global or self._dense,
                stack_metrics=expand_global,
                size="large" if self._dense else "normal",
            )
            outer.addWidget(
                self.row_global,
                stretch=_MAIN_GLOBAL_STRETCH if self._dense else (1 if expand_global else 0),
            )
            if show_velocity:
                self.row_velocity = _WaveRow(
                    "V", C["blue_light"], show_rr=True, expand=True, size="large"
                )
                # Keep the same three metric-column widths as Σ LI, but hide
                # their contents. This aligns both waveform canvases exactly.
                for placeholder in (
                    self.row_velocity.rr_box,
                    self.row_velocity.pct_box,
                    self.row_velocity.trend_box,
                ):
                    for label in placeholder.findChildren(QLabel):
                        label.setVisible(False)
                outer.addWidget(self.row_velocity, stretch=1)
            if show_regional:
                outer.addWidget(_hsep())

        if show_regional:
            if self._dense:
                # Две колонки: L (средний Σ + малые ROI) | R (средний Σ + малые ROI)
                regional = QWidget()
                self._regional_widget = regional
                regional.setStyleSheet("background:transparent;")
                reg_lay = QHBoxLayout(regional)
                reg_lay.setContentsMargins(0, 0, 0, 0)
                reg_lay.setSpacing(0)

                for section, i18n_key, roi_start, agg_color, roi_colors in (
                    ("L", "wave_l_label", roi_count // 2, AERATION_COLOR_L, AERATION_ROI_L),
                    ("R", "wave_r_label", 0, AERATION_COLOR_R, AERATION_ROI_R),
                ):
                    col = QWidget()
                    col.setStyleSheet("background:transparent;")
                    col_lay = QVBoxLayout(col)
                    col_lay.setContentsMargins(4, 2, 4, 2)
                    col_lay.setSpacing(1)
                    self._regional_column_layouts[section] = col_lay

                    hdr = _SectionHeader(i18n_key, section, compact=True)
                    col_lay.addWidget(hdr)
                    if section == "R":
                        self._hdr_r = hdr
                    else:
                        self._hdr_l = hdr

                    agg = _WaveRow(f"Σ {section}", agg_color, size="medium", expand=True)
                    col_lay.addWidget(agg, stretch=_MAIN_AGG_STRETCH)
                    if section == "R":
                        self.row_r_agg = agg
                        target = self.rows_r
                    else:
                        self.row_l_agg = agg
                        target = self.rows_l

                    for i in range(roi_count // 2):
                        idx = roi_start + i
                        row = _WaveRow(
                            f"ROI_{idx + 1}", roi_colors[i % len(roi_colors)],
                            size="compact", expand=True,
                        )
                        col_lay.addWidget(row, stretch=_MAIN_ROI_STRETCH)
                        target.append(row)

                    reg_lay.addWidget(col, stretch=1)
                    if section == "L":
                        reg_lay.addWidget(_vsep())

                outer.addWidget(regional, stretch=_MAIN_REGIONAL_STRETCH)
            else:
                roi_size = "normal"
                self._hdr_l = _SectionHeader("wave_l_label", "L")
                outer.addWidget(self._hdr_l)
                self.row_l_agg = _WaveRow("Σ L", AERATION_COLOR_L, size="medium")
                outer.addWidget(self.row_l_agg)
                for i in range(roi_count // 2):
                    row = _WaveRow(
                        f"ROI_{i + roi_count // 2 + 1}",
                        AERATION_ROI_L[i % len(AERATION_ROI_L)],
                        size=roi_size,
                    )
                    outer.addWidget(row)
                    self.rows_l.append(row)
                outer.addWidget(_hsep())

                self._hdr_r = _SectionHeader("wave_r_label", "R")
                outer.addWidget(self._hdr_r)
                self.row_r_agg = _WaveRow("Σ R", AERATION_COLOR_R, size="medium")
                outer.addWidget(self.row_r_agg)
                for i in range(roi_count // 2):
                    row = _WaveRow(
                        f"ROI_{i+1}", AERATION_ROI_R[i % len(AERATION_ROI_R)], size=roi_size
                    )
                    outer.addWidget(row)
                    self.rows_r.append(row)

        if not expand_global and not self._dense:
            outer.addStretch()

        self.monitoring_moment_bar = _MonitoringMomentBar()
        outer.addWidget(self.monitoring_moment_bar)

        self.btn_event = None
        self._bottom_bar = None
        self._bottom_layout = None
        if show_event_button:
            bottom = QWidget()
            bottom_height = EVENT_MARKER_BTN_HEIGHT + 12
            if bottom_left_widget is not None:
                # The large two-line counters polish to a 101 px size hint;
                # reserve it up front so the 24/32 px typography is not clipped.
                bottom_height = max(bottom_height, 112)
            bottom.setFixedHeight(bottom_height)
            b_lay = QHBoxLayout(bottom)
            b_lay.setContentsMargins(8, 4, 8, 4)
            b_lay.setSpacing(16)
            self._bottom_bar = bottom
            self._bottom_layout = b_lay
            if bottom_left_widget is not None:
                b_lay.addWidget(bottom_left_widget)
            b_lay.addStretch()
            self.btn_event = QPushButton(t("wave_event_marker"))
            configure_event_marker_btn(self.btn_event)
            b_lay.addWidget(self.btn_event)
            outer.addWidget(bottom)

        i18n.language_changed.connect(self.retranslate)

    # ── Public ────────────────────────────────────────────────────────────────

    def set_roi_count(self, roi_count: int) -> None:
        if roi_count == self._roi_count:
            return
        self._roi_count = roi_count
        if not self._show_regional or not self._dense:
            return
        bands = roi_count // 2
        for section, start, target, colors in (
            ("L", bands, self.rows_l, AERATION_ROI_L),
            ("R", 0, self.rows_r, AERATION_ROI_R),
        ):
            layout = self._regional_column_layouts[section]
            for row in target:
                layout.removeWidget(row)
                row.deleteLater()
            target.clear()
            for index in range(bands):
                row = _WaveRow(
                    f"ROI_{start + index + 1}",
                    colors[index % len(colors)],
                    size="compact",
                    expand=True,
                )
                row.trend_box.setVisible(self._trends_visible)
                layout.addWidget(row, stretch=_MAIN_ROI_STRETCH)
                target.append(row)

    def set_trends_visible(self, visible: bool) -> None:
        self._trends_visible = bool(visible)
        for row in (
            self.row_global,
            self.row_r_agg,
            self.row_l_agg,
            *self.rows_r,
            *self.rows_l,
        ):
            if row is not None:
                row.trend_box.setVisible(self._trends_visible)

    def update_all(
        self,
        waves: dict,
        rr: float,
        roi_pcts: list,
        r_pct: float | None = None,
        l_pct: float | None = None,
        trends: dict | None = None,
    ):
        rois = waves["rois"]
        self.monitoring_moment_bar.set_time_values(waves.get("time", ()))
        bands = self._roi_count // 2
        r_agg = np.mean(rois[:bands], axis=0)
        l_agg = np.mean(rois[bands:], axis=0)

        if self.row_global is not None:
            self.row_global.update_data(waves["global"])
            self.row_global.update_pct(100.0 if roi_pcts and any(
                value is not None for value in roi_pcts
            ) else None)
            self.row_global.update_rr(rr)
            if trends:
                self.row_global.update_trend(trends.get("global", 0.0))
        if self.row_velocity is not None:
            self.row_velocity.update_data(waves.get("velocity", np.asarray([])))

        if self.row_r_agg is not None:
            self.row_r_agg.update_data(r_agg)
            if r_pct is not None:
                self.row_r_agg.update_pct(r_pct)
            if trends:
                self.row_r_agg.update_trend(trends.get("r", 0.0))

        if self.row_l_agg is not None:
            self.row_l_agg.update_data(l_agg)
            if l_pct is not None:
                self.row_l_agg.update_pct(l_pct)
            if trends:
                self.row_l_agg.update_trend(trends.get("l", 0.0))

        roi_tr = trends.get("rois", [0.0] * self._roi_count) if trends else [0.0] * self._roi_count
        for i, row in enumerate(self.rows_r):
            row.update_data(rois[i])
            row.update_pct(roi_pcts[i])
            row.update_trend(roi_tr[i] if i < len(roi_tr) else 0.0)
        for i, row in enumerate(self.rows_l):
            row.update_data(rois[i + bands])
            row.update_pct(roi_pcts[i + bands])
            row.update_trend(
                roi_tr[i + bands] if i + bands < len(roi_tr) else 0.0
            )

    def retranslate(self):
        if self._hdr_t is not None:
            self._hdr_t.retranslate()
        if self._hdr_r is not None:
            self._hdr_r.retranslate()
        if self._hdr_l is not None:
            self._hdr_l.retranslate()
        if self.row_global is not None:
            self.row_global.retranslate()
        if self.row_velocity is not None:
            self.row_velocity.retranslate()
        for row in self.rows_r + self.rows_l:
            row.retranslate()
        if self.btn_event is not None:
            self.btn_event.setText(t("wave_event_marker"))

    def set_event_markers(self, events, time_values):
        markers = _relative_markers(events, time_values)
        rows = [
            self.row_global, self.row_velocity, self.row_r_agg, self.row_l_agg,
            *self.rows_r, *self.rows_l,
        ]
        for row in rows:
            if row is not None:
                row.canvas.set_markers(markers)


def _relative_markers(events, time_values) -> tuple[tuple[float, str], ...]:
    times = np.asarray(time_values, dtype=float)
    if times.size == 0:
        return ()
    start, end = float(times[0]), float(times[-1])
    boundary_tolerance = 0.5
    if times.size == 1:
        return tuple(
            (1.0 if float(event.position_seconds) >= start else 0.0, event.event_type)
            for event in events
            if abs(float(event.position_seconds) - start) <= boundary_tolerance
        )
    span = end - start
    if span <= 0:
        return ()
    # The acquisition/filter pipeline and the session clock are independent.
    # During the first frames a valid curve may therefore start a fraction of
    # a second after a just-created operator marker. Keep that boundary marker
    # visible instead of dropping it from the journal/timeline link.
    result = []
    for event in events:
        position = float(event.position_seconds)
        if start - boundary_tolerance <= position <= end + boundary_tolerance:
            result.append((
                max(0.0, min(1.0, (position - start) / span)),
                event.event_type,
            ))
    return tuple(result)
