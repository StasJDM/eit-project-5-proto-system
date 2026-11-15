"""Typed, versioned domain model for the functional EIT prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
import math
import re
from typing import TypeAlias
from uuid import UUID, uuid4


CURRENT_FORMAT_VERSION = 1
ROI_COUNT = 8
ReconstructionMap: TypeAlias = tuple[tuple[float, ...], ...]


class StudyStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class CalibrationStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DataQuality(str, Enum):
    VALID = "valid"
    DEGRADED = "degraded"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class EventCategory(str, Enum):
    MARKER = "marker"
    ADVERSE_EVENT = "adverse_event"
    SYSTEM = "system"
    ALARM = "alarm"


class AlarmSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlarmStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"


class ReportStatus(str, Enum):
    DRAFT = "draft"
    GENERATED = "generated"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """A diagnosis selected from a local bilingual ICD catalogue."""

    code: str
    title: str  # canonical English title; legacy records may contain Russian
    classification: str = "ICD-11"
    title_ru: str | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("diagnosis code must not be blank")
        if not self.title.strip():
            raise ValueError("diagnosis title must not be blank")
        if self.title_ru is not None and not self.title_ru.strip():
            raise ValueError("Russian diagnosis title must not be blank")
        if self.classification not in {"ICD-10", "ICD-11"}:
            raise ValueError("diagnosis classification must be ICD-10 or ICD-11")


@dataclass(frozen=True, slots=True)
class VentilationDetails:
    """Structured mechanical-ventilation data stored with a patient card."""

    enabled: bool = False
    mode: str | None = None
    fio2_percent: float | None = None
    peep_cmh2o: float | None = None

    def __post_init__(self) -> None:
        _validate_optional_text(self.mode, "ventilation.mode")
        _validate_optional_number(self.fio2_percent, "ventilation.fio2_percent", minimum=21.0)
        _validate_optional_number(self.peep_cmh2o, "ventilation.peep_cmh2o", minimum=0.0)
        if self.fio2_percent is not None and self.fio2_percent > 100.0:
            raise ValueError("ventilation.fio2_percent must be <= 100")
        if self.peep_cmh2o is not None and self.peep_cmh2o > 50.0:
            raise ValueError("ventilation.peep_cmh2o must be <= 50")
        if not self.enabled and any(
            value is not None for value in (self.mode, self.fio2_percent, self.peep_cmh2o)
        ):
            raise ValueError("disabled ventilation must not contain parameters")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_uuid(value: UUID, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")


def _validate_utc(value: datetime | None, field_name: str, *, optional: bool = False) -> None:
    if value is None:
        if optional:
            return
        raise ValueError(f"{field_name} is required")
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError(f"{field_name} must be expressed in UTC")


def _validate_format_version(value: int) -> None:
    if value != CURRENT_FORMAT_VERSION:
        raise ValueError(
            f"unsupported format_version={value}; expected {CURRENT_FORMAT_VERSION}"
        )


def _validate_optional_number(
    value: float | None,
    field_name: str,
    *,
    minimum: float | None = None,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite when present")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")


def _validate_optional_text(value: str | None, field_name: str) -> None:
    if value is not None and not value.strip():
        raise ValueError(f"{field_name} must not be blank when present")


@dataclass(frozen=True, slots=True)
class AcquisitionSettings:
    injection_current_ma: float = 1.0
    injection_frequency_khz: float = 200.0
    electrode_count: int = 16
    belt_count: int = 1
    sample_rate_hz: float = 25.0
    electrode_order: str = "right_ccw"
    measurement_sequence: str = "adjacent_fixed"
    two_color_visualization: bool = True
    color_map_id: str = "medical_blue_amber"
    custom_color_low: str = "#29b6d1"
    custom_color_high: str = "#ffc857"
    pathology_detection: bool = True
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        if (
            isinstance(self.injection_current_ma, bool)
            or not isinstance(self.injection_current_ma, (int, float))
            or not math.isfinite(self.injection_current_ma)
            or not 0.5 <= self.injection_current_ma <= 5.0
        ):
            raise ValueError("injection_current_ma must be between 0.5 and 5.0")
        if (
            isinstance(self.injection_frequency_khz, bool)
            or not isinstance(self.injection_frequency_khz, (int, float))
            or not math.isfinite(self.injection_frequency_khz)
            or not 10.0 <= self.injection_frequency_khz <= 500.0
        ):
            raise ValueError("injection_frequency_khz must be between 10 and 500")
        if isinstance(self.electrode_count, bool) or self.electrode_count not in {16, 32}:
            raise ValueError("electrode_count must be 16 or 32")
        if isinstance(self.belt_count, bool) or not 1 <= self.belt_count <= 10:
            raise ValueError("belt_count must be between 1 and 10")
        if (
            isinstance(self.sample_rate_hz, bool)
            or not isinstance(self.sample_rate_hz, (int, float))
            or not math.isfinite(self.sample_rate_hz)
            or self.sample_rate_hz <= 0
        ):
            raise ValueError("sample_rate_hz must be a positive finite value")
        if self.electrode_order not in {
            "right_ccw",
            "right_cw",
            "sternum_cw",
            "sternum_ccw",
        }:
            raise ValueError("unsupported electrode_order")
        if self.measurement_sequence not in {
            "adjacent_fixed",
            "adjacent_rotating",
            "adjacent_reciprocal",
            "adjacent_reversed",
        }:
            raise ValueError("unsupported measurement_sequence")
        if not isinstance(self.two_color_visualization, bool):
            raise TypeError("two_color_visualization must be bool")
        from ..color_maps import CUSTOM_COLOR_MAP_ID, color_map_by_id

        if (
            self.color_map_id != CUSTOM_COLOR_MAP_ID
            and color_map_by_id(self.color_map_id) is None
        ):
            raise ValueError("unsupported color_map_id")
        for value, field_name in (
            (self.custom_color_low, "custom_color_low"),
            (self.custom_color_high, "custom_color_high"),
        ):
            if not isinstance(value, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
                raise ValueError(f"{field_name} must be a #RRGGBB colour")
        if not isinstance(self.pathology_detection, bool):
            raise TypeError("pathology_detection must be bool")


@dataclass(frozen=True, slots=True)
class Patient:
    id: UUID = field(default_factory=uuid4)
    external_id: str | None = None
    medical_record_number: str | None = None
    family_name: str | None = None
    given_name: str | None = None
    middle_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    chest_circumference_cm: float | None = None
    main_diagnosis: Diagnosis | None = None
    accompanying_diagnoses: tuple[Diagnosis, ...] = ()
    ventilation: VentilationDetails = field(default_factory=VentilationDetails)
    created_at_utc: datetime = field(default_factory=utc_now)
    updated_at_utc: datetime = field(default_factory=utc_now)
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_uuid(self.id, "id")
        _validate_utc(self.created_at_utc, "created_at_utc")
        _validate_utc(self.updated_at_utc, "updated_at_utc")
        if self.updated_at_utc < self.created_at_utc:
            raise ValueError("updated_at_utc must not precede created_at_utc")
        for name in (
            "external_id",
            "medical_record_number",
            "family_name",
            "given_name",
            "middle_name",
            "sex",
        ):
            _validate_optional_text(getattr(self, name), name)
        _validate_optional_number(self.weight_kg, "weight_kg", minimum=0.0)
        _validate_optional_number(self.height_cm, "height_cm", minimum=0.0)
        _validate_optional_number(
            self.chest_circumference_cm,
            "chest_circumference_cm",
            minimum=0.0,
        )
        if self.main_diagnosis is not None and not isinstance(self.main_diagnosis, Diagnosis):
            raise TypeError("main_diagnosis must be Diagnosis when present")
        if any(not isinstance(item, Diagnosis) for item in self.accompanying_diagnoses):
            raise TypeError("accompanying_diagnoses must contain Diagnosis values")
        if not isinstance(self.ventilation, VentilationDetails):
            raise TypeError("ventilation must be VentilationDetails")


@dataclass(frozen=True, slots=True)
class CalibrationRecord:
    performed_at_utc: datetime
    status: CalibrationStatus
    usable_measurement_ratio: float
    electrode_levels: tuple[float | None, ...]
    failed_electrodes: tuple[int, ...] = ()
    reason: str | None = None
    simulated: bool = False
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_utc(self.performed_at_utc, "performed_at_utc")
        if not isinstance(self.status, CalibrationStatus):
            raise TypeError("status must be CalibrationStatus")
        if not math.isfinite(self.usable_measurement_ratio) or not 0 <= self.usable_measurement_ratio <= 1:
            raise ValueError("usable_measurement_ratio must be between 0 and 1")
        if len(self.electrode_levels) != 16:
            raise ValueError("electrode_levels must contain exactly 16 values")
        for value in self.electrode_levels:
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError("electrode levels must be null or between 0 and 1")
        if any(number < 1 or number > 16 for number in self.failed_electrodes):
            raise ValueError("failed_electrodes must use numbers from 1 to 16")
        if len(set(self.failed_electrodes)) != len(self.failed_electrodes):
            raise ValueError("failed_electrodes must be unique")
        _validate_optional_text(self.reason, "reason")


@dataclass(frozen=True, slots=True)
class Study:
    patient_id: UUID
    settings: AcquisitionSettings
    id: UUID = field(default_factory=uuid4)
    status: StudyStatus = StudyStatus.DRAFT
    simulated: bool = False
    author: str | None = None
    conclusion: str | None = None
    calibration: CalibrationRecord | None = None
    created_at_utc: datetime = field(default_factory=utc_now)
    updated_at_utc: datetime = field(default_factory=utc_now)
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_uuid(self.id, "id")
        _validate_uuid(self.patient_id, "patient_id")
        if not isinstance(self.settings, AcquisitionSettings):
            raise TypeError("settings must be AcquisitionSettings")
        if not isinstance(self.status, StudyStatus):
            raise TypeError("status must be StudyStatus")
        _validate_optional_text(self.author, "author")
        _validate_optional_text(self.conclusion, "conclusion")
        if self.calibration is not None and not isinstance(self.calibration, CalibrationRecord):
            raise TypeError("calibration must be CalibrationRecord or None")
        _validate_utc(self.created_at_utc, "created_at_utc")
        _validate_utc(self.updated_at_utc, "updated_at_utc")
        if self.updated_at_utc < self.created_at_utc:
            raise ValueError("updated_at_utc must not precede created_at_utc")


@dataclass(frozen=True, slots=True)
class MonitoringSession:
    study_id: UUID
    id: UUID = field(default_factory=uuid4)
    started_at_utc: datetime | None = None
    ended_at_utc: datetime | None = None
    paused_at_utc: datetime | None = None
    accumulated_pause_seconds: float = 0.0
    simulated: bool = False
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_uuid(self.id, "id")
        _validate_uuid(self.study_id, "study_id")
        _validate_utc(self.started_at_utc, "started_at_utc", optional=True)
        _validate_utc(self.ended_at_utc, "ended_at_utc", optional=True)
        _validate_utc(self.paused_at_utc, "paused_at_utc", optional=True)
        if not math.isfinite(self.accumulated_pause_seconds) or self.accumulated_pause_seconds < 0:
            raise ValueError("accumulated_pause_seconds must be non-negative and finite")
        if self.ended_at_utc is not None and self.started_at_utc is None:
            raise ValueError("ended_at_utc requires started_at_utc")
        if (
            self.started_at_utc is not None
            and self.ended_at_utc is not None
            and self.ended_at_utc < self.started_at_utc
        ):
            raise ValueError("ended_at_utc must not precede started_at_utc")
        if self.paused_at_utc is not None and self.started_at_utc is None:
            raise ValueError("paused_at_utc requires started_at_utc")
        if self.paused_at_utc is not None and self.ended_at_utc is not None:
            raise ValueError("completed session must not remain paused")

    def duration_seconds(self, at_utc: datetime | None = None) -> float:
        if self.started_at_utc is None:
            return 0.0
        end = self.ended_at_utc or at_utc or utc_now()
        _validate_utc(end, "at_utc")
        paused = self.accumulated_pause_seconds
        if self.paused_at_utc is not None:
            paused += max(0.0, (end - self.paused_at_utc).total_seconds())
        return max(0.0, (end - self.started_at_utc).total_seconds() - paused)


@dataclass(frozen=True, slots=True)
class EITFrame:
    """Immutable data-source frame for one electrode-belt plane."""

    sequence_number: int
    timestamp_utc: datetime
    belt_index: int
    global_impedance: float
    roi_impedance: tuple[float, ...]
    reconstructed_delta_z: ReconstructionMap
    quality: DataQuality
    simulated: bool
    absolute_conductivity: ReconstructionMap | None = None
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_utc(self.timestamp_utc, "timestamp_utc")
        if self.sequence_number < 0:
            raise ValueError("sequence_number must be non-negative")
        if self.belt_index < 0:
            raise ValueError("belt_index must be non-negative")
        if len(self.roi_impedance) != ROI_COUNT:
            raise ValueError(f"MVP frames must contain exactly {ROI_COUNT} ROI values")
        if not self.reconstructed_delta_z:
            raise ValueError("reconstructed_delta_z must not be empty")
        width = len(self.reconstructed_delta_z[0])
        if width == 0 or any(len(row) != width for row in self.reconstructed_delta_z):
            raise ValueError("reconstructed_delta_z must be a non-empty rectangular map")
        numeric_values = (
            self.global_impedance,
            *self.roi_impedance,
            *(value for row in self.reconstructed_delta_z for value in row),
        )
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("frame values must be finite")
        if not isinstance(self.quality, DataQuality):
            raise TypeError("quality must be DataQuality")
        if self.absolute_conductivity is not None:
            if (
                len(self.absolute_conductivity) != len(self.reconstructed_delta_z)
                or any(len(row) != width for row in self.absolute_conductivity)
            ):
                raise ValueError(
                    "absolute_conductivity must match reconstructed_delta_z shape"
                )
            absolute_values = tuple(
                value for row in self.absolute_conductivity for value in row
            )
            if not all(math.isfinite(value) and value >= 0 for value in absolute_values):
                raise ValueError(
                    "absolute_conductivity values must be finite and non-negative"
                )


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    study_id: UUID
    session_id: UUID
    timestamp_utc: datetime
    respiratory_rate_bpm: float | None
    tvi_au: float | None
    eeli_au: float | None
    eili_au: float | None
    right_left_ratio: float | None
    ventral_dorsal_ratio: float | None
    roi_tvi_au: tuple[float | None, ...]
    quality: DataQuality
    algorithm_version: str
    simulated: bool
    quality_reason: str | None = None
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_uuid(self.study_id, "study_id")
        _validate_uuid(self.session_id, "session_id")
        _validate_utc(self.timestamp_utc, "timestamp_utc")
        if len(self.roi_tvi_au) != ROI_COUNT:
            raise ValueError(f"roi_tvi_au must contain exactly {ROI_COUNT} values")
        _validate_optional_number(
            self.respiratory_rate_bpm,
            "respiratory_rate_bpm",
            minimum=0.0,
        )
        for name in (
            "tvi_au",
            "eeli_au",
            "eili_au",
            "right_left_ratio",
            "ventral_dorsal_ratio",
        ):
            _validate_optional_number(getattr(self, name), name)
        for index, value in enumerate(self.roi_tvi_au):
            _validate_optional_number(value, f"roi_tvi_au[{index}]")
        if not isinstance(self.quality, DataQuality):
            raise TypeError("quality must be DataQuality")
        if not self.algorithm_version.strip():
            raise ValueError("algorithm_version must not be blank")
        _validate_optional_text(self.quality_reason, "quality_reason")


@dataclass(frozen=True, slots=True)
class TrendAggregate:
    """Persisted, versioned trend point for an interval or breath cycle."""

    study_id: UUID
    session_id: UUID
    interval_start_utc: datetime
    interval_end_utc: datetime
    position_seconds: float
    aggregation_kind: str
    sample_count: int
    global_value: float | None
    right_value: float | None
    left_value: float | None
    roi_values: tuple[float | None, ...]
    respiratory_rate_bpm: float | None
    quality: DataQuality
    algorithm_version: str
    simulated: bool
    quality_reason: str | None = None
    metric_values: tuple[tuple[str, float | None], ...] = ()
    id: UUID = field(default_factory=uuid4)
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_uuid(self.id, "id")
        _validate_uuid(self.study_id, "study_id")
        _validate_uuid(self.session_id, "session_id")
        _validate_utc(self.interval_start_utc, "interval_start_utc")
        _validate_utc(self.interval_end_utc, "interval_end_utc")
        if self.interval_end_utc < self.interval_start_utc:
            raise ValueError("interval_end_utc must not precede interval_start_utc")
        if not math.isfinite(self.position_seconds) or self.position_seconds < 0:
            raise ValueError("position_seconds must be non-negative and finite")
        if self.aggregation_kind not in {"interval", "breath_cycle"}:
            raise ValueError("aggregation_kind must be interval or breath_cycle")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")
        if not 2 <= len(self.roi_values) <= 20 or len(self.roi_values) % 2:
            raise ValueError("roi_values must contain an even number of values from 2 to 20")
        for name in ("global_value", "right_value", "left_value"):
            _validate_optional_number(getattr(self, name), name)
        _validate_optional_number(
            self.respiratory_rate_bpm, "respiratory_rate_bpm", minimum=0.0
        )
        for index, value in enumerate(self.roi_values):
            _validate_optional_number(value, f"roi_values[{index}]")
        metric_names: set[str] = set()
        for name, value in self.metric_values:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("trend metric name must not be blank")
            if name in metric_names:
                raise ValueError(f"duplicate trend metric: {name}")
            metric_names.add(name)
            _validate_optional_number(value, f"metric_values[{name!r}]")
        if not isinstance(self.quality, DataQuality):
            raise TypeError("quality must be DataQuality")
        if not self.algorithm_version.strip():
            raise ValueError("algorithm_version must not be blank")
        _validate_optional_text(self.quality_reason, "quality_reason")

    def metric_value(self, name: str) -> float | None:
        """Return a persisted calculated metric without coupling storage to its list."""
        return dict(self.metric_values).get(name)


@dataclass(frozen=True, slots=True)
class Event:
    study_id: UUID
    session_id: UUID
    occurred_at_utc: datetime
    category: EventCategory
    text: str
    event_type: str = "operator_note"
    author: str = "unknown"
    position_seconds: float = 0.0
    corrects_event_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    created_at_utc: datetime = field(default_factory=utc_now)
    simulated: bool = False
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_uuid(self.id, "id")
        _validate_uuid(self.study_id, "study_id")
        _validate_uuid(self.session_id, "session_id")
        _validate_utc(self.occurred_at_utc, "occurred_at_utc")
        _validate_utc(self.created_at_utc, "created_at_utc")
        if not isinstance(self.category, EventCategory):
            raise TypeError("category must be EventCategory")
        if not self.text.strip():
            raise ValueError("text must not be blank")
        if not self.event_type.strip():
            raise ValueError("event_type must not be blank")
        if not self.author.strip():
            raise ValueError("author must not be blank")
        if not math.isfinite(self.position_seconds) or self.position_seconds < 0:
            raise ValueError("position_seconds must be non-negative and finite")
        if self.corrects_event_id is not None:
            _validate_uuid(self.corrects_event_id, "corrects_event_id")
            if self.corrects_event_id == self.id:
                raise ValueError("event cannot correct itself")


@dataclass(frozen=True, slots=True)
class Alarm:
    study_id: UUID
    session_id: UUID
    code: str
    severity: AlarmSeverity
    status: AlarmStatus
    activated_at_utc: datetime
    updated_at_utc: datetime
    id: UUID = field(default_factory=uuid4)
    message: str | None = None
    acknowledged_at_utc: datetime | None = None
    cleared_at_utc: datetime | None = None
    simulated: bool = False
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_uuid(self.id, "id")
        _validate_uuid(self.study_id, "study_id")
        _validate_uuid(self.session_id, "session_id")
        if not self.code.strip():
            raise ValueError("code must not be blank")
        if not isinstance(self.severity, AlarmSeverity):
            raise TypeError("severity must be AlarmSeverity")
        if not isinstance(self.status, AlarmStatus):
            raise TypeError("status must be AlarmStatus")
        _validate_optional_text(self.message, "message")
        for name in (
            "activated_at_utc",
            "updated_at_utc",
            "acknowledged_at_utc",
            "cleared_at_utc",
        ):
            _validate_utc(
                getattr(self, name),
                name,
                optional=name in ("acknowledged_at_utc", "cleared_at_utc"),
            )
        if self.updated_at_utc < self.activated_at_utc:
            raise ValueError("updated_at_utc must not precede activated_at_utc")
        if self.acknowledged_at_utc is not None and self.acknowledged_at_utc < self.activated_at_utc:
            raise ValueError("acknowledged_at_utc must not precede activated_at_utc")
        if self.cleared_at_utc is not None and self.cleared_at_utc < self.activated_at_utc:
            raise ValueError("cleared_at_utc must not precede activated_at_utc")


@dataclass(frozen=True, slots=True)
class Report:
    study_id: UUID
    period_start_utc: datetime
    period_end_utc: datetime
    status: ReportStatus
    template_version: str
    algorithm_versions: tuple[str, ...]
    id: UUID = field(default_factory=uuid4)
    created_at_utc: datetime = field(default_factory=utc_now)
    file_name: str | None = None
    checksum_sha256: str | None = None
    title: str | None = None
    snapshot_json: str | None = None
    simulated: bool = False
    format_version: int = CURRENT_FORMAT_VERSION

    def __post_init__(self) -> None:
        _validate_format_version(self.format_version)
        _validate_uuid(self.id, "id")
        _validate_uuid(self.study_id, "study_id")
        _validate_utc(self.period_start_utc, "period_start_utc")
        _validate_utc(self.period_end_utc, "period_end_utc")
        _validate_utc(self.created_at_utc, "created_at_utc")
        if self.period_end_utc < self.period_start_utc:
            raise ValueError("period_end_utc must not precede period_start_utc")
        if not isinstance(self.status, ReportStatus):
            raise TypeError("status must be ReportStatus")
        if not self.template_version.strip():
            raise ValueError("template_version must not be blank")
        if not self.algorithm_versions or any(
            not version.strip() for version in self.algorithm_versions
        ):
            raise ValueError("algorithm_versions must contain non-blank versions")
        _validate_optional_text(self.file_name, "file_name")
        _validate_optional_text(self.checksum_sha256, "checksum_sha256")
        _validate_optional_text(self.title, "title")
        _validate_optional_text(self.snapshot_json, "snapshot_json")
        if self.snapshot_json is not None:
            import json
            try:
                snapshot = json.loads(self.snapshot_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("snapshot_json must contain valid JSON") from exc
            if not isinstance(snapshot, dict):
                raise ValueError("snapshot_json must contain a JSON object")
        if self.checksum_sha256 is not None and (
            len(self.checksum_sha256) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in self.checksum_sha256)
        ):
            raise ValueError("checksum_sha256 must be a 64-character hexadecimal digest")
