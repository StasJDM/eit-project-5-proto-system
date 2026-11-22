"""Large-format live view for rapid respiratory assessment."""

from __future__ import annotations

from .base_screen import LiveScreen
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..application import EITSettingsService, EngineeringSettings, EngineeringSettingsService
from ..i18n import i18n, t
from ..styles import AERATION_COLOR_T, C
from ..widgets.lung_viz import LungVizWidget
from ..widgets.waveform_panel import WaveformPanel


class _MetricCard(QFrame):
    """A readable medical value card that keeps the unit visually explicit."""

    def __init__(self, title_key: str, unit_key: str | None = None, parent=None):
        super().__init__(parent)
        self._title_key = title_key
        self._unit_key = unit_key
        self.setObjectName("express_metric_card")
        self.setMinimumSize(190, 112)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"""
            QFrame#express_metric_card {{
                background-color:{C['bg_card']};
                border:2px solid {C['border']};
                border-radius:10px;
            }}
            QFrame#express_metric_card QLabel {{
                background:transparent;
                border:none;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.title = QLabel()
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.title.setStyleSheet(
            f"color:{C['text_dim']};font-size:18px;font-weight:600;"
        )
        layout.addWidget(self.title)

        value_row = QHBoxLayout()
        value_row.setSpacing(8)
        value_row.addStretch()
        self.value = QLabel("—")
        self.value.setAlignment(Qt.AlignCenter)
        self.value.setStyleSheet(
            f"color:{C['text']};font-size:46px;font-weight:800;"
        )
        value_row.addWidget(self.value)
        self.unit = QLabel()
        self.unit.setAlignment(Qt.AlignBottom | Qt.AlignLeft)
        self.unit.setStyleSheet(
            f"color:{C['text_dim']};font-size:18px;font-weight:600;padding-bottom:6px;"
        )
        value_row.addWidget(self.unit)
        value_row.addStretch()
        layout.addLayout(value_row, stretch=1)
        self.retranslate()

    def retranslate(self) -> None:
        self.title.setText(t(self._title_key))
        self.unit.setText(t(self._unit_key) if self._unit_key else "")
        self.unit.setVisible(bool(self._unit_key))

    def set_value(self, value, *, decimals: int = 1) -> None:
        if value is None:
            text = "—"
        elif isinstance(value, float):
            text = f"{value:.{decimals}f}"
        else:
            text = str(value)
        self.value.setText(text)


class ExpressMonitoringScreen(LiveScreen):
    """Synchronised lung map, global plethysmogram and core respiratory metrics."""

    def __init__(
        self,
        monitoring,
        parent=None,
        *,
        engineering_settings: EngineeringSettingsService | None = None,
        eit_settings: EITSettingsService | None = None,
    ):
        super().__init__(parent)
        self._monitoring = monitoring
        self._engineering_settings = engineering_settings
        self._display_window_sec = float(
            engineering_settings.current.graph_display_period_seconds
            if engineering_settings is not None
            else 60.0
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(10)

        self._upper_panel = QWidget()
        upper = QHBoxLayout(self._upper_panel)
        upper.setContentsMargins(0, 0, 0, 0)
        upper.setSpacing(12)

        self._lung_panel = QFrame()
        self._lung_panel.setObjectName("express_lung_panel")
        self._lung_panel.setStyleSheet(f"""
            QFrame#express_lung_panel {{
                background-color:{C['bg_panel']};
                border:2px solid {C['border']};
                border-radius:10px;
            }}
        """)
        lung_layout = QVBoxLayout(self._lung_panel)
        lung_layout.setContentsMargins(8, 8, 8, 8)
        self.lung_viz = LungVizWidget()
        self.lung_viz.setMinimumSize(360, 300)
        lung_layout.addWidget(self.lung_viz)
        upper.addWidget(self._lung_panel, stretch=5)

        self._metrics_panel = QWidget()
        metrics = QGridLayout(self._metrics_panel)
        self._metrics_layout = metrics
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(10)
        self.metric_rr = _MetricCard("express_metric_rr", "wave_rr_unit")
        self.metric_tvi = _MetricCard("express_metric_tvi", "express_unit_au")
        self.metric_mvi = _MetricCard("express_metric_mvi", "express_unit_au_min")
        self.metric_eeli = _MetricCard("express_metric_eeli", "express_unit_au")
        self.metric_eili = _MetricCard("express_metric_eili", "express_unit_au")
        self.metric_rl = _MetricCard("express_metric_rl")
        self._metric_cards = (
            self.metric_rr, self.metric_tvi, self.metric_mvi,
            self.metric_eeli, self.metric_eili, self.metric_rl,
        )
        for index, card in enumerate(self._metric_cards):
            metrics.addWidget(card, index // 2, index % 2)
        upper.addWidget(self._metrics_panel, stretch=5)
        root.addWidget(self._upper_panel, stretch=5)

        self._plethysmogram_panel = QFrame()
        self._plethysmogram_panel.setObjectName("express_plethysmogram_panel")
        self._plethysmogram_panel.setStyleSheet(f"""
            QFrame#express_plethysmogram_panel {{
                background-color:{C['bg_wave']};
                border:2px solid {AERATION_COLOR_T};
                border-radius:10px;
            }}
        """)
        pleth_layout = QVBoxLayout(self._plethysmogram_panel)
        pleth_layout.setContentsMargins(4, 4, 4, 4)
        self.plethysmogram = WaveformPanel(
            show_global=True,
            show_regional=False,
            show_event_button=False,
            expand_global=True,
        )
        if self.plethysmogram.row_global.metrics_stack is not None:
            self.plethysmogram.row_global.metrics_stack.hide()
        pleth_layout.addWidget(self.plethysmogram)
        root.addWidget(self._plethysmogram_panel, stretch=4)

        if engineering_settings is not None:
            self._unsubscribe_engineering = engineering_settings.subscribe(
                self._apply_engineering_settings
            )
            self._apply_engineering_settings(engineering_settings.current)
        if eit_settings is not None:
            self._unsubscribe_eit = eit_settings.subscribe(self._apply_eit_settings)
            self._apply_eit_settings(eit_settings.current)

        self.start_refresh(100)
        i18n.language_changed.connect(self.retranslate)
        self._on_paint()

    def _apply_engineering_settings(self, settings: EngineeringSettings) -> None:
        self._display_window_sec = float(settings.graph_display_period_seconds)
        self.plethysmogram.set_fill_enabled(settings.waveform_fill_enabled)
        self.lung_viz.set_section_profile(
            getattr(self._monitoring, "section_profile", settings.section_profile)
        )
        visible = settings.is_element_visible
        metric_visible = settings.is_aeration_metric_visible
        self._lung_panel.setVisible(visible("express_monitoring.lung_map"))
        self._plethysmogram_panel.setVisible(
            visible("express_monitoring.plethysmogram")
        )
        metric_cards = (
            (self.metric_rr, "rr_bpm"),
            (self.metric_tvi, "tvi_au"),
            (self.metric_mvi, "mvi_au_per_min"),
            (self.metric_eeli, "eeli_au"),
            (self.metric_eili, "eili_au"),
            (self.metric_rl, "right_left_ratio"),
        )
        metrics_enabled = visible("express_monitoring.metrics")
        visible_cards = []
        for card, code in metric_cards:
            show = metrics_enabled and metric_visible(code)
            card.setVisible(show)
            if show:
                visible_cards.append(card)
        for index, card in enumerate(visible_cards):
            self._metrics_layout.addWidget(card, index // 2, index % 2)
        self._metrics_panel.setVisible(
            bool(visible_cards)
        )
        self.plethysmogram.set_aeration_metric_visibility(
            settings.hidden_aeration_metrics,
            respiratory_rate_visible=False,
        )

    def _apply_eit_settings(self, settings) -> None:
        self.lung_viz.set_color_settings(
            two_color=settings.two_color_visualization,
            color_map_id=settings.color_map_id,
            custom_low=settings.custom_color_low,
            custom_high=settings.custom_color_high,
        )

    def _scale_widget(self):
        return self.lung_viz

    def _on_paint(self, *_args) -> None:
        active_profile = getattr(self._monitoring, "section_profile", None)
        if active_profile is not None:
            self.lung_viz.set_section_profile(active_profile)
        view = self._monitoring.read_view(self._display_window_sec)
        snap = view.snapshot
        self.lung_viz.update_state(
            snap.phase,
            snap.roi_pct,
            getattr(snap, "reconstruction_map", None),
            getattr(snap, "absolute_conductivity_map", None),
        )
        self.metric_rr.set_value(None if snap.rr is None else round(snap.rr), decimals=0)
        self.metric_tvi.set_value(snap.tvi)
        self.metric_mvi.set_value(snap.mvi)
        self.metric_eeli.set_value(snap.eeli)
        self.metric_eili.set_value(snap.eili)
        self.metric_rl.set_value(snap.lr_ratio)
        self.plethysmogram.update_all(
            view.waveforms,
            snap.rr,
            snap.roi_pct,
            r_pct=snap.r_pct,
            l_pct=snap.l_pct,
            trends={"global": snap.trend_global},
        )

    def retranslate(self, *_args) -> None:
        for card in self._metric_cards:
            card.retranslate()
        self.plethysmogram.retranslate()

