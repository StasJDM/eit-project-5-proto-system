"""Main monitoring screen.

Layout:
  ┌─ left_panel (fixed 265px) ─┬─ waveform_panel (stretch) ─┐
  │  LungVizWidget              │  WaveformPanel              │
  │  numerical parameters       │                             │
  │  start / counters           │                             │
  └────────────────────────────┴────────────────────────────┘
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QGridLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from ..application import (
    EITSettingsService, EngineeringSettings, EngineeringSettingsService, EventMarkerService,
    MonitoringData, MonitoringView,
)
from ..domain import DataQuality
from ..session_timers import SessionTimers
from ..widgets.duration_counters import DurationCounterPair
from ..widgets.lung_viz import LungVizWidget
from ..widgets.waveform_panel import WaveformPanel
from ..styles import (
    C, FONT_SMALL, FONT_LABEL, FONT_MEDICAL_VALUE, start_button_style,
    stop_button_style,
)
from ..i18n import t, i18n

# How often we repaint the screen (100 ms = 10 fps — enough for visual smoothness)
PAINT_MS  = 100


class _ParamBox(QFrame):
    """Параметр слева, значение справа — растягивается на ширину колонки."""

    _H = 52

    def __init__(self, label: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("main_param_box")
        self.setFixedHeight(self._H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(f"""
            QFrame#main_param_box {{
                background-color: {C['bg_card']};
                border: 1px solid {C['border']};
                border-radius: 4px;
            }}
            QFrame#main_param_box QLabel {{
                background: transparent;
                border: none;
            }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(6)

        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        lbl.setStyleSheet(f"color:{C['text_dim']};font-size:{FONT_LABEL}px;")
        lay.addWidget(lbl)

        lay.addStretch(1)

        self._lbl_val = QLabel("—")
        self._lbl_val.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._lbl_val.setMinimumWidth(68)
        self._lbl_val.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_MEDICAL_VALUE}px;font-weight:bold;"
        )
        lay.addWidget(self._lbl_val)

        if unit:
            lbl_u = QLabel(unit)
            lbl_u.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
            lbl_u.setFixedWidth(34)
            lbl_u.setStyleSheet(
                f"color:{C['text_lo']};font-size:{FONT_SMALL}px;"
            )
            lay.addWidget(lbl_u)

    def set_value(self, v, reason: str | None = None):
        if v is None:
            self._lbl_val.setText("—")
        elif isinstance(v, float):
            self._lbl_val.setText(f"{v:.1f}")
        else:
            self._lbl_val.setText(str(v))
        # Карточки обновляются часто, поэтому длинная системная подсказка может
        # неожиданно закрыть графики. Причина качества остаётся видимой в
        # отдельном индикаторе над монитором.
        self.setToolTip("")


# ── Left panel ────────────────────────────────────────────────────────────────

class LeftPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(380)
        self.setStyleSheet(f"""
            background-color: {C['bg_panel']};
            border-right: 2px solid {C['border']};
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 8)
        lay.setSpacing(6)

        # ── Lung visualisation ────────────────────────────────────────────────
        self.lung_viz = LungVizWidget()
        self.lung_viz.setMinimumHeight(300)
        lay.addWidget(self.lung_viz)

        lay.addWidget(self._hsep())

        # ── Numerical parameters ──────────────────────────────────────────────
        grid = QWidget()
        grid_lay = QGridLayout(grid)
        grid_lay.setContentsMargins(2, 2, 2, 2)
        grid_lay.setSpacing(6)
        grid_lay.setColumnStretch(0, 1)
        grid_lay.setColumnStretch(1, 1)

        self.box_t   = _ParamBox("T, %",  "")
        self.box_r   = _ParamBox("R, %",  "")
        self.box_l   = _ParamBox("L, %",  "")
        self.box_lr  = _ParamBox("R/L",   "")
        self.box_vd  = _ParamBox("V/D",   "")
        self.box_tvi = _ParamBox("TVi",  "")

        grid_lay.addWidget(self.box_t,   0, 0)
        grid_lay.addWidget(self.box_r,   1, 0)
        grid_lay.addWidget(self.box_l,   2, 0)
        grid_lay.addWidget(self.box_lr,  0, 1)
        grid_lay.addWidget(self.box_vd,  1, 1)
        grid_lay.addWidget(self.box_tvi, 2, 1)
        lay.addWidget(grid)

        lay.addWidget(self._hsep())

        # ── EELI / EILI ───────────────────────────────────────────────────────
        eeli_row = QWidget()
        eeli_lay = QHBoxLayout(eeli_row)
        eeli_lay.setContentsMargins(0, 0, 0, 0)
        eeli_lay.setSpacing(4)
        self.box_eeli = _ParamBox("EELI")
        self.box_eili = _ParamBox("EILI")
        eeli_lay.addWidget(self.box_eeli, 1)
        eeli_lay.addWidget(self.box_eili, 1)
        lay.addWidget(eeli_row)

        self.box_mvi = _ParamBox("MVi")
        lay.addWidget(self.box_mvi)

        lay.addStretch(1)
        lay.addWidget(self._hsep())

        # ── Start button ──────────────────────────────────────────────────────
        self.btn_start = QPushButton(t("btn_start"))
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(52)
        self.btn_start.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay.addWidget(self.btn_start)

        lay.addSpacing(4)

        # ── Counters ──────────────────────────────────────────────────────────
        self.counters = DurationCounterPair(
            stacked=True, large=True, horizontal=True
        )

        i18n.language_changed.connect(self.retranslate)

    def sync_start(self, running: bool):
        self.btn_start.setProperty("monitoring_running", running)
        if running:
            self.btn_start.setText(t("btn_stop"))
            self.btn_start.setStyleSheet(stop_button_style())
        else:
            self.btn_start.setText(t("btn_start"))
            self.btn_start.setStyleSheet(start_button_style())

    def retranslate(self):
        self.counters.retranslate()
        if not bool(self.btn_start.property("monitoring_running")):
            self.btn_start.setText(t("btn_start"))
        else:
            self.btn_start.setText(t("btn_stop"))

    def _hsep(self) -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"color: {C['border']}; margin: 2px 0;")
        return f

    def update_params(self, snap):
        self.box_t.set_value(snap.t_pct, snap.quality_reason)
        self.box_r.set_value(snap.r_pct, snap.status_for("r_pct").reason)
        self.box_l.set_value(snap.l_pct, snap.status_for("l_pct").reason)
        self.box_lr.set_value(snap.lr_ratio, snap.status_for("rl_ratio").reason)
        self.box_vd.set_value(snap.vd_ratio, snap.status_for("vd_ratio").reason)
        self.box_tvi.set_value(snap.tvi, snap.status_for("tvi").reason)
        self.box_mvi.set_value(snap.mvi, snap.status_for("mvi").reason)
        self.box_eeli.set_value(snap.eeli, snap.status_for("eeli").reason)
        self.box_eili.set_value(snap.eili, snap.status_for("eili").reason)
        self.lung_viz.update_state(
            snap.phase,
            snap.roi_pct,
            getattr(snap, "reconstruction_map", None),
            getattr(snap, "absolute_conductivity_map", None),
        )

    def set_tvi_visible(self, visible: bool) -> None:
        self.box_tvi.setVisible(visible)


# ── Main screen ───────────────────────────────────────────────────────────────

class MainScreen(QWidget):
    """Assembled main monitoring screen backed by an injected read model."""

    def __init__(
        self,
        monitoring: MonitoringData,
        parent=None,
        *,
        display_window_sec: float | None = None,
        marker_service: EventMarkerService | None = None,
        engineering_settings: EngineeringSettingsService | None = None,
        eit_settings: EITSettingsService | None = None,
    ):
        super().__init__(parent)
        self._monitoring = monitoring
        self._marker_service = marker_service
        self._engineering_settings = engineering_settings
        if display_window_sec is None:
            display_window_sec = (
                engineering_settings.current.graph_display_period_seconds
                if engineering_settings is not None else 60.0
            )
        if display_window_sec <= 0:
            raise ValueError("display_window_sec must be positive")
        self._display_window_sec = float(display_window_sec)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._quality_banner = QLabel()
        self._quality_banner.setObjectName("monitoring_quality_banner")
        self._quality_banner.setAlignment(Qt.AlignCenter)
        self._quality_banner.setFixedHeight(28)
        root.addWidget(self._quality_banner)

        body = QWidget()
        lay = QHBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        root.addWidget(body, stretch=1)

        self.left    = LeftPanel()
        self.waves = WaveformPanel(
            show_velocity=True,
            roi_count=(engineering_settings.current.roi_count if engineering_settings else 8),
            bottom_left_widget=self.left.counters,
        )
        if engineering_settings is not None:
            self._unsubscribe_engineering = engineering_settings.subscribe(
                self._apply_engineering_settings
            )
            self._apply_engineering_settings(engineering_settings.current)
        if eit_settings is not None:
            self._unsubscribe_eit_settings = eit_settings.subscribe(
                self._apply_eit_settings
            )
            self._apply_eit_settings(eit_settings.current)

        lay.addWidget(self.left)
        lay.addWidget(self.waves, stretch=1)

        # ── Timers ────────────────────────────────────────────────────────────
        self._paint_timer = QTimer(self)
        self._paint_timer.timeout.connect(self._on_paint)
        self._paint_timer.start(PAINT_MS)

        timers = SessionTimers.instance(self)
        timers.updated.connect(self._on_timers_updated)
        self._on_timers_updated(*timers.values())

        # Начальные значения без пропусков до первого тика таймера
        self._render(self._monitoring.read_view(self._display_window_sec))
        i18n.language_changed.connect(self._on_paint)

    def _apply_engineering_settings(self, settings: EngineeringSettings) -> None:
        self._display_window_sec = float(settings.graph_display_period_seconds)
        self.waves.set_roi_count(settings.roi_count)
        visible = settings.is_element_visible
        self._quality_banner.setVisible(visible("main.quality"))
        self.left.lung_viz.setVisible(visible("main.lung_map"))
        self.left.box_t.setVisible(visible("main.total"))
        for widget in (self.left.box_r, self.left.box_l):
            widget.setVisible(visible("main.regional"))
        self.left.box_lr.setVisible(visible("main.rl"))
        self.left.box_vd.setVisible(visible("main.vd"))
        self.left.box_tvi.setVisible(visible("main.tvi"))
        self.left.box_eeli.setVisible(visible("main.eeli"))
        self.left.box_eili.setVisible(visible("main.eili"))
        self.left.box_mvi.setVisible(visible("main.mvi"))
        for widget in (self.waves._hdr_t, self.waves.row_global):
            if widget is not None:
                widget.setVisible(visible("main.global_waveform"))
        if self.waves.row_velocity is not None:
            self.waves.row_velocity.setVisible(visible("main.velocity"))
        for widget in (
            self.waves._hdr_l, self.waves._hdr_r,
            self.waves.row_l_agg, self.waves.row_r_agg,
            *self.waves.rows_l, *self.waves.rows_r,
        ):
            if widget is not None:
                widget.setVisible(visible("main.regional_waveforms"))
        if self.waves._regional_widget is not None:
            self.waves._regional_widget.setVisible(visible("main.regional_waveforms"))
        self.waves.monitoring_moment_bar.setVisible(
            visible("main.global_waveform")
            or visible("main.regional_waveforms")
            or visible("main.velocity")
        )
        if self.waves.row_global is not None and self.waves.row_global.rr_box is not None:
            self.waves.row_global.rr_box.setVisible(visible("main.respiratory_rate"))
        self.waves.set_trends_visible(visible("main.trends"))
        for widget in (self.left.btn_start, self.left.counters, self.waves.btn_event):
            if widget is not None:
                widget.setVisible(visible("main.controls"))

    def _apply_eit_settings(self, settings) -> None:
        self.left.lung_viz.set_color_settings(
            two_color=settings.two_color_visualization,
            color_map_id=settings.color_map_id,
            custom_low=settings.custom_color_low,
            custom_high=settings.custom_color_high,
        )

    # ── Timer callbacks ───────────────────────────────────────────────────────

    def _on_paint(self, *_args):
        self._render(self._monitoring.read_view(self._display_window_sec))

    def _render(self, view: MonitoringView):
        snap = view.snapshot
        waves = view.waveforms
        self.left.update_params(snap)
        self.waves.update_all(
            waves, snap.rr, snap.roi_pct,
            r_pct=snap.r_pct, l_pct=snap.l_pct,
            trends={
                "global": snap.trend_global,
                "r": snap.trend_r,
                "l": snap.trend_l,
                "rois": snap.roi_trends,
            },
        )
        events = (
            self._marker_service.list_for_current_study()
            if self._marker_service is not None else ()
        )
        self.waves.set_event_markers(events, waves["time"])
        self._update_quality_banner(snap)

    def _update_quality_banner(self, snap):
        # Quality checks are temporarily disabled for the prototype UI.
        quality = DataQuality.VALID
        key = "monitor_quality_valid"
        text = t(key)
        color = {
            DataQuality.VALID: C["ok_hover"],
            DataQuality.DEGRADED: C["warn"],
            DataQuality.STALE: C["warn"],
            DataQuality.UNAVAILABLE: C["alarm"],
        }[quality]
        self._quality_banner.setText(text)
        self._quality_banner.setToolTip(
            f"{t('ui_algorithm_version')}: {snap.algorithm_version}"
        )
        self._quality_banner.setStyleSheet(
            f"background:{C['bg_card']};color:{color};border-bottom:1px solid {color};"
            f"font-size:{FONT_LABEL}px;font-weight:bold;"
        )

    def _on_timers_updated(self, eit: str, es: str):
        self.left.counters.set_values(eit, es)
