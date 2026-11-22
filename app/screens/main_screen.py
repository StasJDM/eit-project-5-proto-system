"""Main monitoring screen.

Layout:
  ┌─ left_panel (up to 540px) ─┬─ waveform_panel (stretch) ─┐
  │  LungVizWidget              │  WaveformPanel              │
  │  numerical parameters       │                             │
  │  start / counters           │                             │
  └────────────────────────────┴────────────────────────────┘
"""

from .base_screen import LiveScreen
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QDialog, QFrame, QSizePolicy, QGridLayout
)
from PySide6.QtCore import QSize, Qt
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
MAIN_LEFT_PANEL_MIN_WIDTH = 380
MAIN_LEFT_PANEL_WIDTH = 450
MAIN_LUNG_VIZ_MIN_HEIGHT = 300
MAIN_LUNG_VIZ_EXPANDED_HEIGHT = 340
MAIN_LUNG_VIZ_EXPAND_AT_PANEL_HEIGHT = 780


class _LungVizWindowOverlay(QDialog):
    """Temporarily hosts the live map over the entire application window."""

    def __init__(self, visualization: LungVizWidget, parent=None):
        super().__init__(parent)
        self.setObjectName("lung_viz_fullscreen_dialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.WindowModal)
        self.setStyleSheet(f"background-color:{C['bg_panel']};")
        self._visualization = visualization
        self._source_parent = visualization.parentWidget()
        self._source_layout = self._source_parent.layout()
        self._source_index = self._source_layout.indexOf(visualization)
        self._restored = False

        self._source_layout.removeWidget(visualization)
        visualization.setParent(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.addStretch()
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("lung_viz_fullscreen_close")
        self.close_button.setAccessibleName(t("lung_fullscreen_close"))
        self.close_button.setToolTip(t("lung_fullscreen_close"))
        self.close_button.setFixedSize(64, 64)
        self.close_button.setStyleSheet(f"""
            QPushButton {{
                background-color:{C['alarm']};color:white;
                border:2px solid #ff6b6b;border-radius:32px;
                font-size:42px;font-weight:bold;padding:0;
            }}
            QPushButton:hover {{ background-color:#c62828; }}
            QPushButton:pressed {{ background-color:#b71c1c; }}
        """)
        self.close_button.clicked.connect(self.close)
        header.addWidget(self.close_button)
        layout.addLayout(header)
        layout.addWidget(visualization, stretch=1)
        i18n.language_changed.connect(self._retranslate)

    def _retranslate(self, _language: str) -> None:
        label = t("lung_fullscreen_close")
        self.close_button.setAccessibleName(label)
        self.close_button.setToolTip(label)

    def _restore_visualization(self) -> None:
        if self._restored:
            return
        self.layout().removeWidget(self._visualization)
        self._visualization.setParent(self._source_parent)
        self._source_layout.insertWidget(self._source_index, self._visualization)
        self._visualization.show()
        self._restored = True

    def closeEvent(self, event) -> None:
        self._restore_visualization()
        super().closeEvent(event)


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

        self._lbl_title = QLabel(label)
        self._lbl_title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._lbl_title.setStyleSheet(f"color:{C['text_dim']};font-size:{FONT_LABEL}px;")
        lay.addWidget(self._lbl_title)

        lay.addStretch(1)

        self._lbl_val = QLabel("—")
        self._lbl_val.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        self._lbl_val.setMinimumWidth(68)
        self._lbl_val.setStyleSheet(
            f"color:{C['text']};font-size:{FONT_MEDICAL_VALUE}px;font-weight:bold;"
        )
        lay.addWidget(self._lbl_val)

        self._lbl_unit = None
        if unit:
            self._lbl_unit = QLabel(unit)
            self._lbl_unit.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
            self._lbl_unit.setMinimumWidth(42)
            self._lbl_unit.setStyleSheet(
                f"color:{C['text_lo']};font-size:{FONT_SMALL}px;"
            )
            lay.addWidget(self._lbl_unit)

    def set_text(self, label: str, unit: str = "") -> None:
        self._lbl_title.setText(label)
        if self._lbl_unit is not None:
            self._lbl_unit.setText(unit)

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
        self.setMinimumWidth(MAIN_LEFT_PANEL_MIN_WIDTH)
        self.setMaximumWidth(MAIN_LEFT_PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setStyleSheet(f"""
            background-color: {C['bg_panel']};
            border-right: 2px solid {C['border']};
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 8)
        lay.setSpacing(6)

        # ── Lung visualisation ────────────────────────────────────────────────
        self.lung_viz = LungVizWidget()
        self.lung_viz.setMinimumHeight(MAIN_LUNG_VIZ_MIN_HEIGHT)
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

        ventilation_row = QWidget()
        ventilation_lay = QHBoxLayout(ventilation_row)
        ventilation_lay.setContentsMargins(0, 0, 0, 0)
        ventilation_lay.setSpacing(4)
        self.box_mvi = _ParamBox("MVi")
        self.box_rr = _ParamBox(t("wave_rr_short"), t("wave_rr_unit"))
        ventilation_lay.addWidget(self.box_mvi, 1)
        ventilation_lay.addWidget(self.box_rr, 1)
        lay.addWidget(ventilation_row)

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
            stacked=True,
            large=True,
            horizontal=True,
            single_line_labels=True,
            label_font_size=FONT_LABEL + 2,
        )

        i18n.language_changed.connect(self.retranslate)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(MAIN_LEFT_PANEL_WIDTH, hint.height())

    def resizeEvent(self, event) -> None:
        target_height = (
            MAIN_LUNG_VIZ_EXPANDED_HEIGHT
            if event.size().height() >= MAIN_LUNG_VIZ_EXPAND_AT_PANEL_HEIGHT
            else MAIN_LUNG_VIZ_MIN_HEIGHT
        )
        if self.lung_viz.minimumHeight() != target_height:
            self.lung_viz.setMinimumHeight(target_height)
        super().resizeEvent(event)

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
        self.box_rr.set_text(t("wave_rr_short"), t("wave_rr_unit"))
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
        rr_value = None if snap.rr is None else f"{snap.rr:.0f}"
        self.box_rr.set_value(rr_value, snap.status_for("rr").reason)
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

class MainScreen(LiveScreen):
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
        self._lung_fullscreen_dialog: _LungVizWindowOverlay | None = None
        self.left.lung_viz.set_fullscreen_activation_enabled(True)
        self.left.lung_viz.activated.connect(self._open_lung_visualization_fullscreen)
        self.waves = WaveformPanel(
            show_velocity=True,
            roi_count=(engineering_settings.current.roi_count if engineering_settings else 8),
            bottom_left_widget=self.left.counters,
        )
        # On the main monitor RR belongs to the numerical-parameter panel.
        # Hide the former graph-side column and its velocity-row spacer so the
        # two graph canvases remain aligned.
        for row in (self.waves.row_global, self.waves.row_velocity):
            if row is not None and row.rr_box is not None:
                row.rr_box.setVisible(False)
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
        self.start_refresh(PAINT_MS)

        timers = SessionTimers.instance(self)
        timers.updated.connect(self._on_timers_updated)
        self._on_timers_updated(*timers.values())

        # Начальные значения без пропусков до первого тика таймера
        self._render(self._monitoring.read_view(self._display_window_sec))
        i18n.language_changed.connect(self._on_paint)

    def _open_lung_visualization_fullscreen(self) -> None:
        dialog = self._lung_fullscreen_dialog
        if dialog is not None and dialog.isVisible():
            return
        dialog = _LungVizWindowOverlay(self.left.lung_viz, self)
        self._lung_fullscreen_dialog = dialog
        dialog.finished.connect(self._clear_lung_fullscreen_dialog)
        host_window = self.window()
        dialog.setGeometry(host_window.geometry())
        dialog.show()

    def _clear_lung_fullscreen_dialog(self, _result: int) -> None:
        self._lung_fullscreen_dialog = None

    def _apply_engineering_settings(self, settings: EngineeringSettings) -> None:
        self._display_window_sec = float(settings.graph_display_period_seconds)
        self.waves.set_roi_count(settings.roi_count)
        self.waves.set_fill_enabled(settings.waveform_fill_enabled)
        self.left.lung_viz.set_section_profile(
            getattr(self._monitoring, "section_profile", settings.section_profile)
        )
        visible = settings.is_element_visible
        metric_visible = settings.is_aeration_metric_visible
        self._quality_banner.setVisible(visible("main.quality"))
        self.left.lung_viz.setVisible(visible("main.lung_map"))
        self.left.box_t.setVisible(
            visible("main.total") and metric_visible("total_percent")
        )
        self.left.box_r.setVisible(
            visible("main.regional") and metric_visible("right_percent")
        )
        self.left.box_l.setVisible(
            visible("main.regional") and metric_visible("left_percent")
        )
        self.left.box_lr.setVisible(
            visible("main.rl") and metric_visible("right_left_ratio")
        )
        self.left.box_vd.setVisible(
            visible("main.vd") and metric_visible("ventral_dorsal_ratio")
        )
        self.left.box_tvi.setVisible(
            visible("main.tvi") and metric_visible("tvi_au")
        )
        self.left.box_eeli.setVisible(
            visible("main.eeli") and metric_visible("eeli_au")
        )
        self.left.box_eili.setVisible(
            visible("main.eili") and metric_visible("eili_au")
        )
        self.left.box_mvi.setVisible(
            visible("main.mvi") and metric_visible("mvi_au_per_min")
        )
        self.left.box_rr.setVisible(
            visible("main.respiratory_rate") and metric_visible("rr_bpm")
        )
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
        self.waves.set_trends_visible(visible("main.trends"))
        self.waves.set_aeration_metric_visibility(
            settings.hidden_aeration_metrics,
            respiratory_rate_visible=False,
        )
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

    def _scale_widget(self):
        return self.left.lung_viz

    def _on_paint(self, *_args):
        active_profile = getattr(self._monitoring, "section_profile", None)
        if active_profile is not None:
            self.left.lung_viz.set_section_profile(active_profile)
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
