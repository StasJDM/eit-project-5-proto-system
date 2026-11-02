"""Application composition root."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from .application import (
    AdverseEventService, BreathingClassificationService, DiagnosisCatalogService, EventBus,
    EITSettingsService, ElectrodeQualityService, EventMarkerService, MonitoringController,
    MonitoringService, PatientService, SessionClockService,
    StudyLifecycleService, StudyPlaybackService, StudyRecordingService,
    TrendService, StudyExportService, MedicalReportService,
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
        source = create_data_source(resolved)
        monitoring = MonitoringService(source, event_bus, settings=eit_settings.current)
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
            repositories.events, lifecycle, event_bus
        )
        trend_service = TrendService(
            repositories.trends, monitoring, lifecycle, event_bus
        )
        adverse_event_service = AdverseEventService(
            repositories.events, lifecycle, event_bus
        )
        breathing_classification = BreathingClassificationService()
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
