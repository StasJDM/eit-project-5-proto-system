"""Application composition root."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from .application import (
    AdverseEventService, BreathClfClassifier, BreathingClassificationService, DiagnosisCatalogService, EventBus,
    EITSettingsService, EngineeringSettingsService, ElectrodeQualityService, EventMarkerService, MonitoringController,
    MonitoringService, PatientService, SessionClockService,
    StudyLifecycleService, StudyPlaybackService, StudyRecordingService,
    TrendService, StudyExportService, MedicalReportService, SpectralBreathingClassifier,
)
from .config import AppConfig
from .data_sources import DataSource, create_data_source
from .storage import (
    AcquisitionRecordingStore, Database, NpzFrameStore, RepositoryBundle,
)
from .technical_logging import get_logger, technical_event


_logger = get_logger("application")


@dataclass(slots=True)
class ApplicationContainer:
    config: AppConfig
    event_bus: EventBus
    data_source: DataSource
    monitoring: MonitoringService
    database: Database | None = None
    repositories: RepositoryBundle | None = None
    frame_store: NpzFrameStore | None = None
    recording_store: AcquisitionRecordingStore | None = None
    patient_service: PatientService | None = None
    diagnosis_catalog: DiagnosisCatalogService | None = None
    eit_settings: EITSettingsService | None = None
    engineering_settings: EngineeringSettingsService | None = None
    study_lifecycle: StudyLifecycleService | None = None
    recording_service: StudyRecordingService | None = None
    playback_service: StudyPlaybackService | None = None
    electrode_quality: ElectrodeQualityService | None = None
    session_clock: SessionClockService | None = None
    monitoring_controller: MonitoringController | None = None
    marker_service: EventMarkerService | None = None
    trend_service: TrendService | None = None
    adverse_event_service: AdverseEventService | None = None
    breathing_classification: BreathingClassificationService | None = None
    export_service: StudyExportService | None = None
    report_service: MedicalReportService | None = None
    startup_diagnostics: tuple[str, ...] = ()

    @classmethod
    def build(cls, config: AppConfig | None = None) -> "ApplicationContainer":
        resolved = config or AppConfig.from_env()
        technical_event(
            _logger,
            logging.INFO,
            "application.starting",
            mode=resolved.data_mode.value,
        )
        resolved.export_dir.mkdir(parents=True, exist_ok=True)
        database = Database(resolved.database_path, resolved.data_mode)
        repositories = RepositoryBundle.build(database)
        frame_store = NpzFrameStore(
            resolved.raw_data_dir,
            simulated=resolved.simulated,
        )
        event_bus = EventBus()
        eit_settings = EITSettingsService(repositories.settings, event_bus)
        engineering_settings = EngineeringSettingsService(repositories.settings, event_bus)
        source = create_data_source(resolved)
        monitoring = MonitoringService(
            source,
            event_bus,
            settings=eit_settings.current,
            roi_count=engineering_settings.current.roi_count,
            peak_detection_method=engineering_settings.current.peak_detection_method,
            peep_silent_threshold_percent=(
                engineering_settings.current.peep_silent_threshold_percent
            ),
            peep_analysis_interval_seconds=(
                engineering_settings.current.peep_analysis_interval_seconds
            ),
            peep_gravity_angle_degrees=(
                engineering_settings.current.peep_gravity_angle_degrees
            ),
            geometry=engineering_settings.current.section_profile,
        )
        def apply_engineering_settings(settings):
            monitoring.set_section_profile(settings.section_profile)
            monitoring.set_aeration_configuration(
                roi_count=settings.roi_count,
                peak_detection_method=settings.peak_detection_method,
            )
            monitoring.configure_peep_analysis(
                silent_threshold_percent=settings.peep_silent_threshold_percent,
                analysis_interval_seconds=settings.peep_analysis_interval_seconds,
                gravity_angle_degrees=settings.peep_gravity_angle_degrees,
            )

        engineering_settings.subscribe(apply_engineering_settings)
        diagnostics = list(resolved.diagnostics)
        technical_event(
            _logger,
            logging.INFO,
            "application.started",
            mode=resolved.data_mode.value,
            source_type=type(source).__name__,
            schema_version=database.schema_version,
        )
        lifecycle = StudyLifecycleService(
            repositories.patients,
            repositories.studies,
            repositories.sessions,
            repositories.settings,
            event_bus,
            simulated=resolved.simulated,
            settings_provider=lambda: eit_settings.current,
            settings_applier=monitoring.configure,
        )
        recording_store = AcquisitionRecordingStore(
            resolved.raw_data_dir / "recordings",
            simulated=resolved.simulated,
        )
        recording_service = StudyRecordingService(
            recording_store, monitoring, lifecycle, event_bus
        )
        playback_service = StudyPlaybackService(
            recording_store,
            monitoring,
            lifecycle,
            event_bus,
            live_source=source,
            live_settings_provider=lambda: eit_settings.current,
        )
        electrode_quality = ElectrodeQualityService(
            monitoring, lifecycle, event_bus
        )
        lifecycle.set_start_validator(electrode_quality.ensure_start_allowed)
        session_clock = SessionClockService(
            lifecycle, repositories.settings
        )
        monitoring_controller = MonitoringController(
            lifecycle, monitoring, session_clock, event_bus
        )
        marker_service = EventMarkerService(
            repositories.events,
            lifecycle,
            event_bus,
            position_provider=lambda: monitoring.current_position_seconds,
        )
        trend_service = TrendService(
            repositories.trends, monitoring, lifecycle, event_bus
        )
        adverse_event_service = AdverseEventService(
            repositories.events, lifecycle, event_bus
        )
        breathing_classifiers = {
            "model": BreathClfClassifier(resolved.breath_model_path),
            "spectral": SpectralBreathingClassifier(),
        }
        breathing_classification = BreathingClassificationService(
            breathing_classifiers[
                engineering_settings.current.breathing_identification_method
            ],
            allow_experimental=True,
        )
        engineering_settings.subscribe(
            lambda settings: breathing_classification.set_classifier(
                breathing_classifiers[settings.breathing_identification_method],
                allow_experimental=True,
            )
        )
        export_service = StudyExportService(repositories, recording_store)
        report_service = MedicalReportService(repositories, resolved.export_dir / "reports")
        return cls(
            config=resolved,
            event_bus=event_bus,
            data_source=source,
            monitoring=monitoring,
            database=database,
            repositories=repositories,
            frame_store=frame_store,
            recording_store=recording_store,
            patient_service=PatientService(repositories.patients),
            diagnosis_catalog=DiagnosisCatalogService(repositories.settings, event_bus),
            eit_settings=eit_settings,
            engineering_settings=engineering_settings,
            study_lifecycle=lifecycle,
            recording_service=recording_service,
            playback_service=playback_service,
            electrode_quality=electrode_quality,
            session_clock=session_clock,
            monitoring_controller=monitoring_controller,
            marker_service=marker_service,
            trend_service=trend_service,
            adverse_event_service=adverse_event_service,
            breathing_classification=breathing_classification,
            export_service=export_service,
            report_service=report_service,
            startup_diagnostics=tuple(diagnostics),
        )

    def shutdown(self) -> None:
        technical_event(_logger, logging.INFO, "application.stopping")
        if self.monitoring_controller is not None:
            self.monitoring_controller.shutdown()
        else:
            self.monitoring.stop()
        if self.recording_service is not None:
            self.recording_service.close()
        if self.trend_service is not None:
            self.trend_service.close()
        if self.database is not None:
            self.database.close()
        technical_event(_logger, logging.INFO, "application.stopped")
