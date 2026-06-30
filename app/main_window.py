"""MainWindow — top-level application window.

Structure:
  ┌── left (header + screen_stack, stretch) ──┬── nav_panel (full height) ──┐
  │  ┌── header_bar (full width) ───────────┐ │  NavPanel                   │
  │  │                                      │ │  (10 nav buttons)           │
  │  ├── screen_stack (stretch) ────────────┤ │                             │
  │  │  MainScreen / PatientScreen / …      │ │                             │
  │  └──────────────────────────────────────┘ │                             │
  └───────────────────────────────────────────┴─────────────────────────────┘
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget
)
from PySide6.QtCore import Qt

from .styles import stylesheet
from .session_timers import SessionTimers
from .widgets.header_bar import HeaderBar
from .widgets.nav_panel import NavPanel

from .screens.main_screen       import MainScreen
from .screens.patient_screen    import PatientScreen
from .screens.analysis_screen   import AnalysisScreen
from .screens.trends_screen     import TrendsScreen
from .screens.eit_settings_screen import EITSettingsScreen
from .screens.service_info_screen import ServiceInfoScreen
from .screens.system_info_screen  import SystemInfoScreen
from .screens.export_data_screen  import ExportDataScreen
from .screens.reports_screen      import ReportsScreen
from .screens.debug_screen        import DebugScreen


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ЭИТ — Монитор пациента")
        self.setMinimumSize(1280, 768)
        self.setStyleSheet(stylesheet())

        SessionTimers.instance(self)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left column: header + screen stack ────────────────────────────────
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)
        root.addWidget(left, stretch=1)

        self.header = HeaderBar()
        left_lay.addWidget(self.header)

        # ── Screen stack ──────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        left_lay.addWidget(self._stack, stretch=1)

        # ── Navigation panel (full height, right side) ────────────────────────
        self._nav = NavPanel()
        self._nav.screen_requested.connect(self._switch_screen)
        root.addWidget(self._nav)

        # ── Register screens ──────────────────────────────────────────────────
        self._screens: dict[str, QWidget] = {}
        self._register("main",         MainScreen())
        self._register("patient",      PatientScreen())
        self._register("analysis",     AnalysisScreen())
        self._register("trends",       TrendsScreen())
        self._register("eit_settings", EITSettingsScreen())
        self._register("service",      ServiceInfoScreen())
        self._register("system",       SystemInfoScreen())
        self._register("export",       ExportDataScreen())
        self._register("reports",      ReportsScreen())
        self._register("debug",        DebugScreen())

        self._switch_screen("main")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _register(self, key: str, widget: QWidget):
        self._screens[key] = widget
        self._stack.addWidget(widget)

    def _switch_screen(self, key: str):
        if key in self._screens:
            self._stack.setCurrentWidget(self._screens[key])
            self._nav.set_active(key)
