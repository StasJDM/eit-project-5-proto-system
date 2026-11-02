"""Application services and ports used by the Qt presentation layer."""

from .events import ApplicationEvent, EventBus, EventType
from .monitoring import (
    MonitoringData, MonitoringMode, MonitoringService, MonitoringSnapshot,
    MonitoringView,
)
from .acquisition import (
    AcquisitionMetrics,
    AcquisitionPipeline,
    AcquisitionSnapshot,
    SourceFrame,
)
from .aeration import (
    ALGORITHM_VERSION,
    AerationAlgorithmParameters,
    AerationProcessor,
    AerationResult,
    MetricAvailability,
    ProcessedAerationSample,
    calculate_aeration_metrics,
)
from .ports import (
    EventRepository,
    PatientRepository,
    SettingsRepository,
    StudyRepository,
    MonitoringSessionRepository,
    TrendRepository,
)
from .studies import (
    InvalidStudyTransition,
    StudyLifecycleError,
    StudyLifecycleService,
    StudyHistoryEntry,
)
from .patients import (
    DuplicatePatientError,
    PatientDraft,
    PatientService,
    PatientValidationError,
    full_years,
)
from .eit_settings import ACQUISITION_SETTINGS_KEY, EITSettingsService
from .recording import StudyRecordingService
from .playback import PlaybackSnapshot, StudyPlaybackError, StudyPlaybackService
from .signal_quality import (
    ElectrodeContact, ElectrodeContactStatus, ElectrodeQualityBlockedError,
    ElectrodeQualityService, ElectrodeQualitySnapshot, MINIMUM_USABLE_RATIO,
)
from .monitoring_controller import MonitoringController, MonitoringControllerError
from .markers import EventMarkerError, EventMarkerService, MARKER_TYPES
from .adverse_events import (
    ADVERSE_EVENT_TYPES, AdverseEventError, AdverseEventService,
)
from .trends import (
    TREND_ALGORITHM_VERSION, TREND_INTERVAL_SECONDS, TrendSeries, TrendService,
)
from .breathing_classification import (
    BreathingClass, BreathingClassificationResult, BreathingClassificationService,
    ClassificationMetrics, LabeledBreathingSample, ManualBreathingAssessment,
    ValidatedBreathingClassifier,
)
from .session_clock import (
    ELECTRODE_USAGE_SECONDS_SETTING, SessionClockService, SessionClockSnapshot,
)
from .exporting import (
    CSV_DELIMITER, CSV_ENCODING, EXCEL_MAX_ROWS, EXPORT_CATEGORIES,
    EXPORT_SCHEMA_VERSION, ExportError, ExportEstimate, ExportResult,
    StudyExportService, validate_xlsx,
)
from .reporting import MedicalReportService, REPORT_TEMPLATE_VERSION, ReportError
from .icd11 import (
    DEFAULT_DIAGNOSIS_CLASSIFICATION,
    DIAGNOSIS_CLASSIFICATION_SETTING,
    DiagnosisCatalogService,
    ICD10_CATALOGUE,
    ICD10_RELEASE,
    ICD10_SOURCE_URL,
    ICD11_CATALOGUE,
    ICD11_RELEASE,
    ICD11_SOURCE_URL,
    resolve_diagnosis,
    resolve_icd11,
    search_diagnoses,
    search_icd11,
)

__all__ = [
    "ApplicationEvent",
    "AcquisitionMetrics",
    "AcquisitionPipeline",
    "AcquisitionSnapshot",
    "ALGORITHM_VERSION",
    "AerationAlgorithmParameters",
    "AerationProcessor",
    "AerationResult",
    "MetricAvailability",
    "EventBus",
    "EventRepository",
    "EventType",
    "MonitoringData",
    "MonitoringMode",
    "MonitoringService",
    "MonitoringSnapshot",
    "MonitoringView",
    "PatientRepository",
    "ProcessedAerationSample",
    "DuplicatePatientError",
    "PatientDraft",
    "PatientService",
    "PatientValidationError",
    "ACQUISITION_SETTINGS_KEY",
    "EITSettingsService",
    "full_years",
    "ICD11_CATALOGUE",
    "ICD11_RELEASE",
    "ICD11_SOURCE_URL",
    "ICD10_CATALOGUE",
    "ICD10_RELEASE",
    "ICD10_SOURCE_URL",
    "DEFAULT_DIAGNOSIS_CLASSIFICATION",
    "DIAGNOSIS_CLASSIFICATION_SETTING",
    "DiagnosisCatalogService",
    "resolve_diagnosis",
    "search_diagnoses",
    "resolve_icd11",
    "search_icd11",
    "SettingsRepository",
    "StudyRecordingService",
    "PlaybackSnapshot",
    "StudyPlaybackError",
    "StudyPlaybackService",
    "ElectrodeContact",
    "ElectrodeContactStatus",
    "ElectrodeQualityBlockedError",
    "ElectrodeQualityService",
    "ElectrodeQualitySnapshot",
    "MINIMUM_USABLE_RATIO",
    "MonitoringController",
    "MonitoringControllerError",
    "EventMarkerError",
    "EventMarkerService",
    "MARKER_TYPES",
    "ADVERSE_EVENT_TYPES",
    "AdverseEventError",
    "AdverseEventService",
    "ELECTRODE_USAGE_SECONDS_SETTING",
    "SessionClockService",
    "SessionClockSnapshot",
    "SourceFrame",
    "calculate_aeration_metrics",
    "StudyRepository",
    "MonitoringSessionRepository",
    "TrendRepository",
    "TREND_ALGORITHM_VERSION",
    "TREND_INTERVAL_SECONDS",
    "TrendSeries",
    "TrendService",
    "BreathingClass",
    "BreathingClassificationResult",
    "BreathingClassificationService",
    "ClassificationMetrics",
    "LabeledBreathingSample",
    "ManualBreathingAssessment",
    "ValidatedBreathingClassifier",
    "InvalidStudyTransition",
    "StudyLifecycleError",
    "StudyLifecycleService",
    "StudyHistoryEntry",
    "CSV_DELIMITER",
    "CSV_ENCODING",
    "EXCEL_MAX_ROWS",
    "EXPORT_CATEGORIES",
    "EXPORT_SCHEMA_VERSION",
    "ExportError",
    "ExportEstimate",
    "ExportResult",
    "StudyExportService",
    "validate_xlsx",
    "MedicalReportService",
    "REPORT_TEMPLATE_VERSION",
    "ReportError",
]
