"""Explicit JSON-compatible serialization for versioned domain models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, TypeAlias
from uuid import UUID

from .models import (
    CURRENT_FORMAT_VERSION,
    AcquisitionSettings,
    Alarm,
    AlarmSeverity,
    AlarmStatus,
    CalibrationRecord,
    CalibrationStatus,
    DataQuality,
    Diagnosis,
    EITFrame,
    Event,
    EventCategory,
    MetricSnapshot,
    MonitoringSession,
    Patient,
    Report,
    ReportStatus,
    Study,
    StudyStatus,
    TrendAggregate,
    VentilationDetails,
)


DomainModel: TypeAlias = (
    AcquisitionSettings
    | Patient
    | Study
    | CalibrationRecord
    | MonitoringSession
    | EITFrame
    | MetricSnapshot
    | TrendAggregate
    | Event
    | Alarm
    | Report
)


def serialize_model(model: DomainModel) -> dict[str, Any]:
    common = {
        "model_type": type(model).__name__,
        "format_version": model.format_version,
    }
    if isinstance(model, AcquisitionSettings):
        return common | {
            "injection_current_ma": model.injection_current_ma,
            "injection_frequency_khz": model.injection_frequency_khz,
            "electrode_count": model.electrode_count,
            "belt_count": model.belt_count,
            "sample_rate_hz": model.sample_rate_hz,
            "electrode_order": model.electrode_order,
            "measurement_sequence": model.measurement_sequence,
            "two_color_visualization": model.two_color_visualization,
            "pathology_detection": model.pathology_detection,
        }
    if isinstance(model, Patient):
        return common | {
            "id": str(model.id),
            "external_id": model.external_id,
            "medical_record_number": model.medical_record_number,
            "family_name": model.family_name,
            "given_name": model.given_name,
            "middle_name": model.middle_name,
            "date_of_birth": _date_text(model.date_of_birth),
            "sex": model.sex,
            "weight_kg": model.weight_kg,
            "height_cm": model.height_cm,
            "chest_circumference_cm": model.chest_circumference_cm,
            "main_diagnosis": _diagnosis_data(model.main_diagnosis),
            "accompanying_diagnoses": [
                _diagnosis_data(item) for item in model.accompanying_diagnoses
            ],
            "ventilation": {
                "enabled": model.ventilation.enabled,
                "mode": model.ventilation.mode,
                "fio2_percent": model.ventilation.fio2_percent,
                "peep_cmh2o": model.ventilation.peep_cmh2o,
            },
            "created_at_utc": _datetime_text(model.created_at_utc),
            "updated_at_utc": _datetime_text(model.updated_at_utc),
        }
    if isinstance(model, Study):
        return common | {
            "id": str(model.id),
            "patient_id": str(model.patient_id),
            "settings": serialize_model(model.settings),
            "status": model.status.value,
            "simulated": model.simulated,
            "author": model.author,
            "conclusion": model.conclusion,
            "calibration": (
                serialize_model(model.calibration) if model.calibration is not None else None
            ),
            "created_at_utc": _datetime_text(model.created_at_utc),
            "updated_at_utc": _datetime_text(model.updated_at_utc),
        }
    if isinstance(model, CalibrationRecord):
        return common | {
            "performed_at_utc": _datetime_text(model.performed_at_utc),
            "status": model.status.value,
            "usable_measurement_ratio": model.usable_measurement_ratio,
            "electrode_levels": list(model.electrode_levels),
            "failed_electrodes": list(model.failed_electrodes),
            "reason": model.reason,
            "simulated": model.simulated,
        }
    if isinstance(model, MonitoringSession):
        return common | {
            "id": str(model.id),
            "study_id": str(model.study_id),
            "started_at_utc": _datetime_text(model.started_at_utc),
            "ended_at_utc": _datetime_text(model.ended_at_utc),
            "paused_at_utc": _datetime_text(model.paused_at_utc),
            "accumulated_pause_seconds": model.accumulated_pause_seconds,
            "simulated": model.simulated,
        }
    if isinstance(model, EITFrame):
        return common | {
            "sequence_number": model.sequence_number,
            "timestamp_utc": _datetime_text(model.timestamp_utc),
            "belt_index": model.belt_index,
            "global_impedance": model.global_impedance,
            "roi_impedance": list(model.roi_impedance),
            "reconstructed_delta_z": [list(row) for row in model.reconstructed_delta_z],
            "absolute_conductivity": (
                [list(row) for row in model.absolute_conductivity]
                if model.absolute_conductivity is not None
                else None
            ),
            "quality": model.quality.value,
            "simulated": model.simulated,
        }
    if isinstance(model, MetricSnapshot):
        return common | {
            "study_id": str(model.study_id),
            "session_id": str(model.session_id),
            "timestamp_utc": _datetime_text(model.timestamp_utc),
            "respiratory_rate_bpm": model.respiratory_rate_bpm,
            "tvi_au": model.tvi_au,
            "eeli_au": model.eeli_au,
            "eili_au": model.eili_au,
            "right_left_ratio": model.right_left_ratio,
            "ventral_dorsal_ratio": model.ventral_dorsal_ratio,
            "roi_tvi_au": list(model.roi_tvi_au),
            "quality": model.quality.value,
            "quality_reason": model.quality_reason,
            "algorithm_version": model.algorithm_version,
            "simulated": model.simulated,
        }
    if isinstance(model, TrendAggregate):
        return common | {
            "id": str(model.id),
            "study_id": str(model.study_id),
            "session_id": str(model.session_id),
            "interval_start_utc": _datetime_text(model.interval_start_utc),
            "interval_end_utc": _datetime_text(model.interval_end_utc),
            "position_seconds": model.position_seconds,
            "aggregation_kind": model.aggregation_kind,
            "sample_count": model.sample_count,
            "global_value": model.global_value,
            "right_value": model.right_value,
            "left_value": model.left_value,
            "roi_values": list(model.roi_values),
            "respiratory_rate_bpm": model.respiratory_rate_bpm,
            "quality": model.quality.value,
            "quality_reason": model.quality_reason,
            "algorithm_version": model.algorithm_version,
            "simulated": model.simulated,
        }
    if isinstance(model, Event):
        return common | {
            "id": str(model.id),
            "study_id": str(model.study_id),
            "session_id": str(model.session_id),
            "occurred_at_utc": _datetime_text(model.occurred_at_utc),
            "created_at_utc": _datetime_text(model.created_at_utc),
            "category": model.category.value,
            "text": model.text,
            "event_type": model.event_type,
            "author": model.author,
            "position_seconds": model.position_seconds,
            "corrects_event_id": (
                str(model.corrects_event_id) if model.corrects_event_id else None
            ),
            "simulated": model.simulated,
        }
    if isinstance(model, Alarm):
        return common | {
            "id": str(model.id),
            "study_id": str(model.study_id),
            "session_id": str(model.session_id),
            "code": model.code,
            "severity": model.severity.value,
            "status": model.status.value,
            "message": model.message,
            "activated_at_utc": _datetime_text(model.activated_at_utc),
            "updated_at_utc": _datetime_text(model.updated_at_utc),
            "acknowledged_at_utc": _datetime_text(model.acknowledged_at_utc),
            "cleared_at_utc": _datetime_text(model.cleared_at_utc),
            "simulated": model.simulated,
        }
    if isinstance(model, Report):
        return common | {
            "id": str(model.id),
            "study_id": str(model.study_id),
            "period_start_utc": _datetime_text(model.period_start_utc),
            "period_end_utc": _datetime_text(model.period_end_utc),
            "status": model.status.value,
            "template_version": model.template_version,
            "algorithm_versions": list(model.algorithm_versions),
            "created_at_utc": _datetime_text(model.created_at_utc),
            "file_name": model.file_name,
            "checksum_sha256": model.checksum_sha256,
            "title": model.title,
            "snapshot_json": model.snapshot_json,
            "simulated": model.simulated,
        }
    raise TypeError(f"unsupported domain model: {type(model).__name__}")


def deserialize_model(data: dict[str, Any]) -> DomainModel:
    model_type = _required(data, "model_type", str)
    version = _required(data, "format_version", int)
    if version != CURRENT_FORMAT_VERSION:
        raise ValueError(
            f"unsupported format_version={version}; expected {CURRENT_FORMAT_VERSION}"
        )
    kwargs = {"format_version": version}

    if model_type == "AcquisitionSettings":
        return AcquisitionSettings(
            injection_current_ma=float(data.get("injection_current_ma", 1.0)),
            injection_frequency_khz=float(data.get("injection_frequency_khz", 200.0)),
            electrode_count=_required(data, "electrode_count", int),
            belt_count=_required(data, "belt_count", int),
            sample_rate_hz=_number(data, "sample_rate_hz"),
            electrode_order=data.get("electrode_order", "right_ccw"),
            measurement_sequence=data.get("measurement_sequence", "adjacent_fixed"),
            two_color_visualization=data.get("two_color_visualization", True),
            pathology_detection=data.get("pathology_detection", True),
            **kwargs,
        )
    if model_type == "Patient":
        diagnoses_data = data.get("accompanying_diagnoses", [])
        if not isinstance(diagnoses_data, list):
            raise ValueError("accompanying_diagnoses must be a list")
        ventilation_data = data.get("ventilation", {"enabled": False})
        if not isinstance(ventilation_data, dict):
            raise ValueError("ventilation must be an object")
        return Patient(
            id=_uuid(data, "id"),
            external_id=_optional(data, "external_id", str),
            medical_record_number=_optional(data, "medical_record_number", str),
            family_name=_optional(data, "family_name", str),
            given_name=_optional(data, "given_name", str),
            middle_name=_optional(data, "middle_name", str),
            date_of_birth=_date(data, "date_of_birth"),
            sex=_optional(data, "sex", str),
            weight_kg=_optional_number(data, "weight_kg"),
            height_cm=_optional_number(data, "height_cm"),
            chest_circumference_cm=_optional_number(data, "chest_circumference_cm"),
            main_diagnosis=_diagnosis(data.get("main_diagnosis")),
            accompanying_diagnoses=tuple(_diagnosis(item) for item in diagnoses_data),
            ventilation=VentilationDetails(
                enabled=ventilation_data.get("enabled", False),
                mode=_optional(ventilation_data, "mode", str),
                fio2_percent=_optional_number(ventilation_data, "fio2_percent"),
                peep_cmh2o=_optional_number(ventilation_data, "peep_cmh2o"),
            ),
            created_at_utc=_datetime(data, "created_at_utc"),
            updated_at_utc=_datetime(data, "updated_at_utc"),
            **kwargs,
        )
    if model_type == "Study":
        settings_data = _required(data, "settings", dict)
        settings = deserialize_model(settings_data)
        if not isinstance(settings, AcquisitionSettings):
            raise ValueError("Study.settings must contain AcquisitionSettings")
        calibration_data = data.get("calibration")
        calibration = None
        if calibration_data is not None:
            if not isinstance(calibration_data, dict):
                raise ValueError("Study.calibration must be an object or null")
            calibration = deserialize_model(calibration_data)
            if not isinstance(calibration, CalibrationRecord):
                raise ValueError("Study.calibration must contain CalibrationRecord")
        return Study(
            id=_uuid(data, "id"),
            patient_id=_uuid(data, "patient_id"),
            settings=settings,
            status=StudyStatus(_required(data, "status", str)),
            simulated=_required(data, "simulated", bool),
            author=_optional(data, "author", str),
            conclusion=_optional(data, "conclusion", str),
            calibration=calibration,
            created_at_utc=_datetime(data, "created_at_utc"),
            updated_at_utc=_datetime(data, "updated_at_utc"),
            **kwargs,
        )
    if model_type == "CalibrationRecord":
        levels = _required(data, "electrode_levels", list)
        failed = _required(data, "failed_electrodes", list)
        if any(value is not None and isinstance(value, bool) for value in levels):
            raise ValueError("electrode_levels must contain numbers or null")
        if any(type(value) is not int for value in failed):
            raise ValueError("failed_electrodes must contain integers")
        return CalibrationRecord(
            performed_at_utc=_datetime(data, "performed_at_utc"),
            status=CalibrationStatus(_required(data, "status", str)),
            usable_measurement_ratio=_number(data, "usable_measurement_ratio"),
            electrode_levels=tuple(
                None if value is None else float(value) for value in levels
            ),
            failed_electrodes=tuple(failed),
            reason=_optional(data, "reason", str),
            simulated=_required(data, "simulated", bool),
            **kwargs,
        )
    if model_type == "MonitoringSession":
        return MonitoringSession(
            id=_uuid(data, "id"),
            study_id=_uuid(data, "study_id"),
            started_at_utc=_optional_datetime(data, "started_at_utc"),
            ended_at_utc=_optional_datetime(data, "ended_at_utc"),
            paused_at_utc=_optional_datetime(data, "paused_at_utc"),
            accumulated_pause_seconds=float(data.get("accumulated_pause_seconds", 0.0)),
            simulated=_required(data, "simulated", bool),
            **kwargs,
        )
    if model_type == "EITFrame":
        roi_values = _required(data, "roi_impedance", list)
        reconstruction = _required(data, "reconstructed_delta_z", list)
        absolute = data.get("absolute_conductivity")
        if absolute is not None and not isinstance(absolute, list):
            raise ValueError("absolute_conductivity must be a list or null")
        return EITFrame(
            sequence_number=_required(data, "sequence_number", int),
            timestamp_utc=_datetime(data, "timestamp_utc"),
            belt_index=_required(data, "belt_index", int),
            global_impedance=_number(data, "global_impedance"),
            roi_impedance=tuple(_list_numbers(roi_values, "roi_impedance")),
            reconstructed_delta_z=tuple(
                tuple(_list_numbers(row, "reconstructed_delta_z row"))
                for row in reconstruction
            ),
            absolute_conductivity=(
                tuple(
                    tuple(_list_numbers(row, "absolute_conductivity row"))
                    for row in absolute
                )
                if absolute is not None
                else None
            ),
            quality=DataQuality(_required(data, "quality", str)),
            simulated=_required(data, "simulated", bool),
            **kwargs,
        )
    if model_type == "MetricSnapshot":
        # Accept the former ``roi_tiv_au`` key when reading existing records.
        roi_key = "roi_tvi_au" if "roi_tvi_au" in data else "roi_tiv_au"
        roi_values = _required(data, roi_key, list)
        return MetricSnapshot(
            study_id=_uuid(data, "study_id"),
            session_id=_uuid(data, "session_id"),
            timestamp_utc=_datetime(data, "timestamp_utc"),
            respiratory_rate_bpm=_optional_number(data, "respiratory_rate_bpm"),
            tvi_au=_optional_number(data, "tvi_au"),
            eeli_au=_optional_number(data, "eeli_au"),
            eili_au=_optional_number(data, "eili_au"),
            right_left_ratio=_optional_number(data, "right_left_ratio"),
            ventral_dorsal_ratio=_optional_number(data, "ventral_dorsal_ratio"),
            roi_tvi_au=tuple(_list_optional_numbers(roi_values, roi_key)),
            quality=DataQuality(_required(data, "quality", str)),
            quality_reason=_optional(data, "quality_reason", str),
            algorithm_version=_required(data, "algorithm_version", str),
            simulated=_required(data, "simulated", bool),
            **kwargs,
        )
    if model_type == "TrendAggregate":
        return TrendAggregate(
            id=UUID(data["id"]),
            study_id=UUID(data["study_id"]),
            session_id=UUID(data["session_id"]),
            interval_start_utc=_datetime(data, "interval_start_utc"),
            interval_end_utc=_datetime(data, "interval_end_utc"),
            position_seconds=float(data["position_seconds"]),
            aggregation_kind=str(data["aggregation_kind"]),
            sample_count=int(data["sample_count"]),
            global_value=_optional_number(data, "global_value"),
            right_value=_optional_number(data, "right_value"),
            left_value=_optional_number(data, "left_value"),
            roi_values=tuple(_list_optional_numbers(
                _required(data, "roi_values", list), "roi_values"
            )),
            respiratory_rate_bpm=_optional_number(data, "respiratory_rate_bpm"),
            quality=DataQuality(data["quality"]),
            quality_reason=data.get("quality_reason"),
            algorithm_version=str(data["algorithm_version"]),
            simulated=bool(data["simulated"]),
            format_version=version,
        )
    if model_type == "Event":
        return Event(
            id=_uuid(data, "id"),
            study_id=_uuid(data, "study_id"),
            session_id=_uuid(data, "session_id"),
            occurred_at_utc=_datetime(data, "occurred_at_utc"),
            created_at_utc=_datetime(data, "created_at_utc"),
            category=EventCategory(_required(data, "category", str)),
            text=_required(data, "text", str),
            event_type=_optional(data, "event_type", str) or "operator_note",
            author=_optional(data, "author", str) or "unknown",
            position_seconds=_optional_number(data, "position_seconds") or 0.0,
            corrects_event_id=(
                UUID(value) if (value := _optional(data, "corrects_event_id", str)) else None
            ),
            simulated=_required(data, "simulated", bool),
            **kwargs,
        )
    if model_type == "Alarm":
        return Alarm(
            id=_uuid(data, "id"),
            study_id=_uuid(data, "study_id"),
            session_id=_uuid(data, "session_id"),
            code=_required(data, "code", str),
            severity=AlarmSeverity(_required(data, "severity", str)),
            status=AlarmStatus(_required(data, "status", str)),
            message=_optional(data, "message", str),
            activated_at_utc=_datetime(data, "activated_at_utc"),
            updated_at_utc=_datetime(data, "updated_at_utc"),
            acknowledged_at_utc=_optional_datetime(data, "acknowledged_at_utc"),
            cleared_at_utc=_optional_datetime(data, "cleared_at_utc"),
            simulated=_required(data, "simulated", bool),
            **kwargs,
        )
    if model_type == "Report":
        versions = _required(data, "algorithm_versions", list)
        if any(not isinstance(value, str) for value in versions):
            raise ValueError("algorithm_versions must contain strings")
        return Report(
            id=_uuid(data, "id"),
            study_id=_uuid(data, "study_id"),
            period_start_utc=_datetime(data, "period_start_utc"),
            period_end_utc=_datetime(data, "period_end_utc"),
            status=ReportStatus(_required(data, "status", str)),
            template_version=_required(data, "template_version", str),
            algorithm_versions=tuple(versions),
            created_at_utc=_datetime(data, "created_at_utc"),
            file_name=_optional(data, "file_name", str),
            checksum_sha256=_optional(data, "checksum_sha256", str),
            title=_optional(data, "title", str),
            snapshot_json=_optional(data, "snapshot_json", str),
            simulated=_required(data, "simulated", bool),
            **kwargs,
        )
    raise ValueError(f"unknown model_type={model_type!r}")


def _required(data: dict[str, Any], key: str, expected: type) -> Any:
    if key not in data:
        raise ValueError(f"missing required field: {key}")
    value = data[key]
    if type(value) is not expected:
        raise ValueError(f"{key} must be {expected.__name__}")
    return value


def _optional(data: dict[str, Any], key: str, expected: type) -> Any:
    value = data.get(key)
    if value is not None and type(value) is not expected:
        raise ValueError(f"{key} must be {expected.__name__} or null")
    return value


def _number(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def _optional_number(data: dict[str, Any], key: str) -> float | None:
    if data.get(key) is None:
        return None
    return _number(data, key)


def _uuid(data: dict[str, Any], key: str) -> UUID:
    try:
        return UUID(_required(data, key, str))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a valid UUID") from exc


def _datetime_text(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat().replace("+00:00", "Z")


def _datetime(data: dict[str, Any], key: str) -> datetime:
    value = _required(data, key, str)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO-8601 datetime") from exc


def _optional_datetime(data: dict[str, Any], key: str) -> datetime | None:
    if data.get(key) is None:
        return None
    return _datetime(data, key)


def _date_text(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _date(data: dict[str, Any], key: str) -> date | None:
    value = _optional(data, key, str)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO-8601 date") from exc


def _diagnosis_data(value: Diagnosis | None) -> dict[str, str] | None:
    if value is None:
        return None
    result = {
        "code": value.code,
        "title": value.title,
        "classification": value.classification,
    }
    if value.title_ru is not None:
        result["title_ru"] = value.title_ru
    return result


def _diagnosis(value: Any) -> Diagnosis | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("diagnosis must be an object or null")
    return Diagnosis(
        code=_required(value, "code", str),
        title=_required(value, "title", str),
        # Patient payloads written before the configurable catalogue feature
        # contained only ICD-11 diagnoses.
        classification=value.get("classification", "ICD-11"),
        title_ru=value.get("title_ru"),
    )


def _list_numbers(values: list[Any], field_name: str) -> list[float]:
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} must contain numbers")
        result.append(float(value))
    return result


def _list_optional_numbers(values: list[Any], field_name: str) -> list[float | None]:
    result: list[float | None] = []
    for value in values:
        if value is None:
            result.append(None)
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} must contain numbers or null")
        else:
            result.append(float(value))
    return result
