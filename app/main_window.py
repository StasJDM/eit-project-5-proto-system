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
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QMessageBox, QPushButton, QLabel, QComboBox, QSlider,
)
from PySide6.QtCore import Qt, QTimer

from .container import ApplicationContainer
from .application import (
    ElectrodeQualityBlockedError, EventMarkerError, EventType, StudyLifecycleError,
)
from .domain import StudyStatus
from .i18n import i18n, t
from .styles import C, start_button_style
from .styles import stylesheet
from .session_timers import SessionTimers, fmt_duration
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
from .screens.event_marker_dialog import EventMarkerDialog


class _PlaybackBar(QWidget):
    """Compact controls shown only for an immutable historical recording."""

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self._service = service
        self.setFixedHeight(42)
        self.setStyleSheet(
            f"background:#2a1800;border-bottom:1px solid {C['warn']};color:white;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        self._title = QLabel(t("playback_read_only"))
        layout.addWidget(self._title)
        self._position = QLabel("00:00 / 00:00")
        layout.addWidget(self._position)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 1)
        self._slider.sliderReleased.connect(self._seek)
        layout.addWidget(self._slider, stretch=1)
        self._speed = QComboBox()
        for value in (0.5, 1.0, 2.0, 4.0):
            self._speed.addItem(f"{value:g}×", value)
        self._speed.setCurrentIndex(1)
        self._speed.currentIndexChanged.connect(self._change_speed)
        layout.addWidget(self._speed)
        self._pause = QPushButton(t("playback_pause"))
        self._pause.clicked.connect(self._toggle_pause)
        layout.addWidget(self._pause)
        self._close = QPushButton(t("playback_close"))
        if self._service is not None:
            self._close.clicked.connect(self._service.close)
        layout.addWidget(self._close)
        self.hide()

    def sync(self) -> None:
        if self._service is None:
            self.hide()
            return
        state = self._service.snapshot
        self.setVisible(state.active)
        if not state.active:
            return
        maximum = max(1, round(state.duration_seconds * 1000))
        self._slider.setMaximum(maximum)
        if not self._slider.isSliderDown():
            self._slider.setValue(min(maximum, round(state.position_seconds * 1000)))
        self._position.setText(
            f"{fmt_duration(round(state.position_seconds))} / "
            f"{fmt_duration(round(state.duration_seconds))}"
        )
        self._pause.setText(t("playback_resume") if state.paused else t("playback_pause"))

    def _seek(self) -> None:
        if self._service is not None:
            self._service.seek(self._slider.value() / 1000.0)

    def _change_speed(self, index: int) -> None:
        if self._service is not None and self._service.snapshot.active:
            self._service.set_speed(float(self._speed.itemData(index)))

    def _toggle_pause(self) -> None:
        if self._service is None:
            return
        if self._service.snapshot.paused:
            self._service.resume()
        else:
            self._service.pause()


class MainWindow(QMainWindow):

    def __init__(self, container: ApplicationContainer | None = None):
        super().__init__()
        self._owns_container = container is None
        self._container = container or ApplicationContainer.build()
        self.setWindowTitle(t("app_title"))
        self.setMinimumSize(1280, 768)
        self.setStyleSheet(stylesheet())

        SessionTimers.instance(self).bind(self._container.session_clock)

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

        self._playback_bar = _PlaybackBar(self._container.playback_service, self)
        left_lay.addWidget(self._playback_bar)

        # ── Screen stack ──────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        left_lay.addWidget(self._stack, stretch=1)

        # ── Navigation panel (full height, right side) ────────────────────────
        self._nav = NavPanel()
        self._nav.screen_requested.connect(self._switch_screen)
        root.addWidget(self._nav)

        # ── Register screens ──────────────────────────────────────────────────
        self._screens: dict[str, QWidget] = {}
        self._register(
            "main",
            MainScreen(
                self._container.monitoring,
                marker_service=self._container.marker_service,
                engineering_settings=self._container.engineering_settings,
            ),
        )
        self._register(
            "patient",
            PatientScreen(
                self._container.patient_service,
                self._container.repositories.studies if self._container.repositories else None,
                self._container.diagnosis_catalog,
                self._container.study_lifecycle,
                self._container.playback_service,
            ),
        )
        self._register(
            "analysis",
            AnalysisScreen(
                self._container.monitoring,
                marker_service=self._container.marker_service,
                classification_service=self._container.breathing_classification,
                engineering_settings=self._container.engineering_settings,
            ),
        )
        self._register(
            "trends",
            TrendsScreen(
                self._container.monitoring,
                marker_service=self._container.marker_service,
                trend_service=self._container.trend_service,
                study_repository=(self._container.repositories.studies if self._container.repositories else None),
                event_repository=(self._container.repositories.events if self._container.repositories else None),
                lifecycle=self._container.study_lifecycle,
            ),
        )
        self._register(
            "eit_settings",
            EITSettingsScreen(
                self._container.diagnosis_catalog,
                self._container.eit_settings,
            ),
        )
        self._register(
            "service", ServiceInfoScreen(
                self._container.marker_service,
                self._container.adverse_event_service,
            )
        )
        self._register(
            "system",
            SystemInfoScreen(
                self._container.config,
                self._container.engineering_settings,
            ),
        )
        self._register(
            "export",
            ExportDataScreen(self._container.export_service, self._container.config.export_dir),
        )
        self._register("reports", ReportsScreen(self._container.report_service))
        self._register("debug",        DebugScreen(self._container.electrode_quality))

        self._wire_study_controls()
        self._wire_event_marker_controls()
        self._unsubscribe_study = self._container.event_bus.subscribe(
            EventType.STUDY_CHANGED, self._on_study_changed
        )
        self._unsubscribe_playback = self._container.event_bus.subscribe(
            EventType.PLAYBACK_CHANGED, self._on_playback_changed
        )
        self._screens["patient"].playback_started.connect(
            lambda: self._switch_screen("main")
        )
        self._sync_study_controls()
        self._restore_selected_patient()

        self._playback_ui_timer = QTimer(self)
        self._playback_ui_timer.timeout.connect(self._playback_bar.sync)
        self._playback_ui_timer.start(200)

        self._switch_screen("main")
        i18n.language_changed.connect(
            lambda _language: self.setWindowTitle(t("app_title"))
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _register(self, key: str, widget: QWidget):
        self._screens[key] = widget
        self._stack.addWidget(widget)

    def _switch_screen(self, key: str):
        current = self._stack.currentWidget()
        patient_screen = self._screens.get("patient")
        if (
            current is patient_screen
            and key != "patient"
            and isinstance(patient_screen, PatientScreen)
            and not patient_screen.confirm_discard_changes()
        ):
            self._nav.set_active("patient")
            return
        if key in self._screens:
            if key == "patient" and isinstance(patient_screen, PatientScreen):
                patient_screen.refresh_diagnosis_catalog()
            service_screen = self._screens.get("service")
            if key == "service" and isinstance(service_screen, ServiceInfoScreen):
                service_screen.refresh()
            export_screen = self._screens.get("export")
            if key == "export" and isinstance(export_screen, ExportDataScreen):
                export_screen.refresh()
            reports_screen = self._screens.get("reports")
            if key == "reports" and isinstance(reports_screen, ReportsScreen):
                reports_screen.refresh()
            self._stack.setCurrentWidget(self._screens[key])
            self._nav.set_active(key)

    def _wire_study_controls(self):
        main = self._screens["main"]
        patient = self._screens["patient"]
        analysis = self._screens["analysis"]
        trends = self._screens["trends"]
        candidates = [
            main.left.btn_start,
            patient._btn_start,
            *(tab.btn_start for tab in analysis._all_tabs()),
            trends.bottom.btn_start,
            self._screens["eit_settings"]._btn_start,
            self._screens["export"]._btn_start,
            self._screens["reports"]._btn_start,
            self._screens["debug"]._btn_start,
        ]
        self._study_buttons: list[QPushButton] = candidates
        for button in self._study_buttons:
            button.clicked.connect(self._toggle_study)

    def _wire_event_marker_controls(self):
        main = self._screens["main"]
        analysis = self._screens["analysis"]
        trends = self._screens["trends"]
        candidates = [
            main.waves.btn_event,
            *analysis.event_buttons,
            trends.bottom.btn_marker,
        ]
        self._marker_buttons = [button for button in candidates if button is not None]
        for button in self._marker_buttons:
            button.clicked.connect(self._open_event_marker_dialog)

    def _open_event_marker_dialog(self):
        service = self._container.marker_service
        lifecycle = self._container.study_lifecycle
        if (
            service is None
            or lifecycle is None
            or lifecycle.status not in {StudyStatus.RUNNING, StudyStatus.PAUSED}
        ):
            QMessageBox.warning(self, t("study_action_error_title"), t("marker_unavailable"))
            return
        dialog = EventMarkerDialog(
            service.current_position_seconds,
            service.default_author,
            parent=self,
        )
        if dialog.exec() != dialog.Accepted:
            return
        values = dialog.values()
        try:
            service.create(values.event_type, values.description, values.author)
        except EventMarkerError:
            QMessageBox.warning(self, t("study_action_error_title"), t("marker_unavailable"))
            return
        service_screen = self._screens.get("service")
        if isinstance(service_screen, ServiceInfoScreen):
            service_screen.refresh()

    def _toggle_study(self):
        lifecycle = self._container.study_lifecycle
        controller = self._container.monitoring_controller
        if lifecycle is None:
            return
        try:
            if lifecycle.status in {
                None, StudyStatus.DRAFT, StudyStatus.COMPLETED, StudyStatus.FAILED,
            }:
                self._prepare_study_for_immediate_start()
            if lifecycle.status is StudyStatus.READY:
                controller.start() if controller is not None else lifecycle.start()
            elif lifecycle.status is StudyStatus.PAUSED:
                controller.resume() if controller is not None else lifecycle.resume()
            elif lifecycle.status is StudyStatus.RUNNING:
                dialog = QMessageBox(
                    QMessageBox.Question,
                    t("study_stop_title"),
                    t("study_stop_confirm"),
                    QMessageBox.Yes | QMessageBox.No,
                    self,
                )
                dialog.setDefaultButton(QMessageBox.No)
                dialog.button(QMessageBox.Yes).setText(t("common_yes"))
                dialog.button(QMessageBox.No).setText(t("common_no"))
                answer = dialog.exec()
                if answer == QMessageBox.Yes:
                    controller.stop() if controller is not None else lifecycle.stop()
            else:
                QMessageBox.warning(
                    self, t("study_action_error_title"), t("study_prepare_first")
                )
        except ElectrodeQualityBlockedError:
            QMessageBox.warning(
                self, t("study_action_error_title"), t("study_contact_quality_blocked")
            )
        except StudyLifecycleError:
            QMessageBox.warning(
                self, t("study_action_error_title"), t("study_invalid_transition")
            )
        self._sync_study_controls()

    def _prepare_study_for_immediate_start(self) -> None:
        lifecycle = self._container.study_lifecycle
        if lifecycle is None:
            raise StudyLifecycleError("study lifecycle is unavailable")
        if lifecycle.selected_patient_id is None:
            patient_service = self._container.patient_service
            if patient_service is None:
                raise StudyLifecycleError("patient service is unavailable")
            patient = patient_service.ensure_automatic_patient()
            lifecycle.select_patient(patient.id)
        if lifecycle.status in {None, StudyStatus.COMPLETED, StudyStatus.FAILED}:
            lifecycle.create_study()
        if lifecycle.status is StudyStatus.DRAFT:
            lifecycle.prepare()

    def _sync_study_controls(self):
        lifecycle = self._container.study_lifecycle
        status = lifecycle.status if lifecycle is not None else None
        running = status is StudyStatus.RUNNING
        enabled = lifecycle is not None
        playback_active = (
            self._container.playback_service is not None
            and self._container.playback_service.snapshot.active
        )
        if playback_active:
            enabled = False
        for button in getattr(self, "_study_buttons", ()):
            button.setEnabled(enabled)
            button.setText(t("btn_stop") if running else t("btn_start"))
            if running:
                button.setStyleSheet(
                    f"QPushButton{{background:{C['alarm']};color:white;font-weight:bold;}}"
                )
            else:
                button.setStyleSheet(start_button_style())
        main = self._screens.get("main")
        if isinstance(main, MainScreen):
            main.left.sync_start(running)
        for button in getattr(self, "_marker_buttons", ()):
            button.setEnabled(
                status in {StudyStatus.RUNNING, StudyStatus.PAUSED}
                and not playback_active
            )
        analysis = self._screens.get("analysis")
        if isinstance(analysis, AnalysisScreen):
            analysis.sync_start(running)

    def _on_study_changed(self, _event):
        self._sync_study_controls()
        patient = self._screens.get("patient")
        if isinstance(patient, PatientScreen):
            patient.refresh_history()

    def _on_playback_changed(self, _event):
        active = (
            self._container.playback_service is not None
            and self._container.playback_service.snapshot.active
        )
        self.header.set_playback_mode(active)
        self._playback_bar.sync()
        self._sync_study_controls()

    def _restore_selected_patient(self):
        lifecycle = self._container.study_lifecycle
        repositories = self._container.repositories
        if lifecycle is None or repositories is None or lifecycle.selected_patient_id is None:
            return
        patient = repositories.patients.get(lifecycle.selected_patient_id)
        screen = self._screens.get("patient")
        if patient is not None and isinstance(screen, PatientScreen):
            screen.load_patient(patient)

    def closeEvent(self, event):
        patient_screen = self._screens.get("patient")
        if (
            isinstance(patient_screen, PatientScreen)
            and not patient_screen.confirm_discard_changes()
        ):
            event.ignore()
            return
        if self._owns_container:
            self._container.shutdown()
        if hasattr(self, "_unsubscribe_study"):
            self._unsubscribe_study()
        if hasattr(self, "_unsubscribe_playback"):
            self._unsubscribe_playback()
        super().closeEvent(event)
