"""Standalone PEEP screen shown as a top-level navigation item."""

from .base_screen import LiveScreen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..application import EngineeringSettings, EngineeringSettingsService
from ..i18n import i18n
from ..session_timers import SessionTimers
from .analysis_screen import PAINT_MS, PeepTab


class PeepScreen(LiveScreen):
    """Live Silent Spaces map and PEEP-oriented distribution metrics."""

    def __init__(
        self,
        monitoring,
        parent=None,
        *,
        engineering_settings: EngineeringSettingsService | None = None,
    ):
        super().__init__(parent)
        self._monitoring = monitoring
        self._analysis_interval_seconds = 15.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._tab = PeepTab()
        layout.addWidget(self._tab)

        self.btn_start = self._tab.btn_start
        self.event_buttons = (self._tab.btn_event,)

        self._unsubscribe_engineering = None
        if engineering_settings is not None:
            self._unsubscribe_engineering = engineering_settings.subscribe(
                self._apply_engineering_settings
            )
            self._apply_engineering_settings(engineering_settings.current)

        self.start_refresh(PAINT_MS)

        timers = SessionTimers.instance(self)
        timers.updated.connect(self._tab.set_counters)
        self._tab.set_counters(*timers.values())
        i18n.language_changed.connect(self._tab.retranslate)

    def _apply_engineering_settings(self, settings: EngineeringSettings) -> None:
        self._analysis_interval_seconds = float(
            settings.peep_analysis_interval_seconds
        )

    def _on_paint(self) -> None:
        if hasattr(self._monitoring, "read_view"):
            view = self._monitoring.read_view(self._analysis_interval_seconds)
            snapshot, waveforms = view.snapshot, view.waveforms
        else:
            snapshot = self._monitoring.snapshot
            waveforms = self._monitoring.get_waveforms(
                self._analysis_interval_seconds
            )
        self._tab.update_data(snapshot, waveforms)

    def sync_start(self, running: bool) -> None:
        self._tab.sync_start(running)

    def closeEvent(self, event) -> None:
        if self._unsubscribe_engineering is not None:
            self._unsubscribe_engineering()
            self._unsubscribe_engineering = None
        super().closeEvent(event)
