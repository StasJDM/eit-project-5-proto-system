"""Strict compatibility contract for the JSON used by sibling EIT projects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from typing import Any, Mapping

from ..domain import DataQuality
from .base import TimestampSource


ADJACENT_16_PROTOCOL_ID = "adjacent-16x13-hypothesis-v1"
ELECTRODE_COUNT = 16
CHANNEL_COUNT = ELECTRODE_COUNT * (ELECTRODE_COUNT - 3)
_ROOT_METADATA_KEYS = {"param", "metadata", "_metadata", "protocol", "schema_version"}


class JSONMeasurementFormatError(ValueError):
    """The recording does not satisfy the observed inter-project JSON format."""


@dataclass(frozen=True, slots=True)
class RawMeasurementFrame:
    sequence_number: int
    timestamp_utc: datetime
    channel_values: tuple[float, ...]
    protocol_id: str = ADJACENT_16_PROTOCOL_ID
    belt_index: int = 0
    quality: DataQuality = DataQuality.VALID
    timestamp_source: TimestampSource = TimestampSource.SYNTHESIZED
    simulated: bool = False

    def __post_init__(self) -> None:
        if self.sequence_number < 0:
            raise ValueError("sequence_number must be non-negative")
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be timezone-aware")
        if self.timestamp_utc.utcoffset() != timezone.utc.utcoffset(self.timestamp_utc):
            raise ValueError("timestamp_utc must be expressed in UTC")
        if len(self.channel_values) != CHANNEL_COUNT:
            raise ValueError(f"channel_values must contain exactly {CHANNEL_COUNT} values")
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in self.channel_values
        ):
            raise TypeError("channel_values must be numeric")
        if not all(math.isfinite(value) for value in self.channel_values):
            raise ValueError("channel_values must be finite")
        if self.belt_index < 0:
            raise ValueError("belt_index must be non-negative")
        if not self.protocol_id.strip():
            raise ValueError("protocol_id must not be blank")


@dataclass(frozen=True, slots=True)
class JSONMeasurementRecording:
    frames: tuple[RawMeasurementFrame, ...]
    frame_rate_hz: float
    frame_rate_source: str
    electrode_count: int
    channel_count: int
    protocol_id: str
    excitation_frequency_khz: float | None
    excitation_current_ma: float | None
    raw_param: str
    metadata: Mapping[str, Any]


class _JSONObject(list):
    """Preserves object pairs so duplicate JSON keys can be rejected."""


def load_json_measurement_recording(
    path: str | Path,
    *,
    fallback_frame_rate_hz: float = 25.0,
    recording_started_at_utc: datetime | None = None,
    simulated: bool = False,
) -> JSONMeasurementRecording:
    source_path = Path(path)
    try:
        with source_path.open("r", encoding="utf-8") as source:
            raw = json.load(source, object_pairs_hook=_JSONObject)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JSONMeasurementFormatError(f"cannot read EIT JSON: {exc}") from exc
    payload = _convert_json_object(raw, "root")
    if not isinstance(payload, dict):
        raise JSONMeasurementFormatError("JSON root must be an object")
    if recording_started_at_utc is None:
        recording_started_at_utc = datetime.fromtimestamp(
            source_path.stat().st_mtime, tz=timezone.utc
        )
    return _parse_recording(
        payload,
        fallback_frame_rate_hz=fallback_frame_rate_hz,
        recording_started_at_utc=recording_started_at_utc,
        simulated=simulated,
    )


def parse_json_measurement_recording(
    payload: Mapping[str, Any],
    *,
    fallback_frame_rate_hz: float = 25.0,
    recording_started_at_utc: datetime | None = None,
    simulated: bool = False,
) -> JSONMeasurementRecording:
    """Parse an already decoded payload; useful for transport adapters and tests."""
    return _parse_recording(
        dict(payload),
        fallback_frame_rate_hz=fallback_frame_rate_hz,
        recording_started_at_utc=recording_started_at_utc or datetime(1970, 1, 1, tzinfo=timezone.utc),
        simulated=simulated,
    )


def _parse_recording(
    payload: dict[str, Any],
    *,
    fallback_frame_rate_hz: float,
    recording_started_at_utc: datetime,
    simulated: bool,
) -> JSONMeasurementRecording:
    fallback_frame_rate_hz = _positive_number(
        fallback_frame_rate_hz, "fallback_frame_rate_hz"
    )
    start = _utc(recording_started_at_utc, "recording_started_at_utc")

    metadata = _metadata(payload)
    electrode_count = _optional_int(metadata.get("n_electrodes"), ELECTRODE_COUNT)
    channel_count = _optional_int(metadata.get("n_channels"), CHANNEL_COUNT)
    if electrode_count != ELECTRODE_COUNT or channel_count != CHANNEL_COUNT:
        raise JSONMeasurementFormatError(
            f"only the observed {ELECTRODE_COUNT}-electrode/{CHANNEL_COUNT}-channel contract is supported"
        )
    pattern = metadata.get("current_pattern") or metadata.get("protocol")
    if pattern not in (None, "", "adjacent", ADJACENT_16_PROTOCOL_ID):
        raise JSONMeasurementFormatError(f"unsupported measurement pattern: {pattern!r}")
    protocol_value = payload.get("protocol")
    if isinstance(protocol_value, dict):
        protocol_value = protocol_value.get("id")
    protocol_id = str(protocol_value or ADJACENT_16_PROTOCOL_ID)

    frame_items: list[tuple[int, Any]] = []
    for key, value in payload.items():
        if key in _ROOT_METADATA_KEYS:
            continue
        if not isinstance(key, str) or not key.isdigit() or str(int(key)) != key:
            raise JSONMeasurementFormatError(f"unknown root field or invalid frame key: {key!r}")
        frame_items.append((int(key), value))
    frame_items.sort(key=lambda item: item[0])
    if not frame_items:
        raise JSONMeasurementFormatError("recording contains no frames")
    numbers = [number for number, _ in frame_items]
    if numbers != list(range(len(numbers))):
        missing = sorted(set(range(numbers[-1] + 1)).difference(numbers))
        raise JSONMeasurementFormatError(f"frame sequence must be contiguous from 0; missing={missing[:10]}")

    frame_rate_hz, frame_rate_source = _frame_rate(metadata, len(frame_items), fallback_frame_rate_hz)
    timestamp_source = TimestampSource.SYNTHESIZED
    recorded_at = metadata.get("recorded_at")
    if recorded_at is not None:
        start = _parse_timestamp(recorded_at)
        timestamp_source = TimestampSource.RECORDING_METADATA

    frames = tuple(
        RawMeasurementFrame(
            sequence_number=number,
            timestamp_utc=start + timedelta(seconds=number / frame_rate_hz),
            channel_values=_frame_values(number, value),
            protocol_id=protocol_id,
            timestamp_source=timestamp_source,
            simulated=simulated,
        )
        for number, value in frame_items
    )
    raw_param = payload.get("param", "")
    if not isinstance(raw_param, str):
        raise JSONMeasurementFormatError("param must be a string")
    param_parts = raw_param.split("_") if raw_param else []
    frequency = _optional_positive(metadata.get("frequency_khz"))
    current = _optional_positive(metadata.get("current_ma"))
    if frequency is None:
        frequency = _param_number(param_parts, 2)
    if current is None:
        current = _param_number(param_parts, 3)

    return JSONMeasurementRecording(
        frames=frames,
        frame_rate_hz=frame_rate_hz,
        frame_rate_source=frame_rate_source,
        electrode_count=electrode_count,
        channel_count=channel_count,
        protocol_id=protocol_id,
        excitation_frequency_khz=frequency,
        excitation_current_ma=current,
        raw_param=raw_param,
        metadata=metadata,
    )


def _metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    legacy = payload.get("_metadata")
    current = payload.get("metadata")
    if legacy is not None and current is not None:
        raise JSONMeasurementFormatError("use either metadata or _metadata, not both")
    value = current if current is not None else legacy if legacy is not None else {}
    if not isinstance(value, dict):
        raise JSONMeasurementFormatError("metadata must be an object")
    return dict(value)


def _frame_values(sequence: int, value: Any) -> tuple[float, ...]:
    if isinstance(value, dict) and set(value) == {"0"}:
        value = value["0"]
    if not isinstance(value, list):
        raise JSONMeasurementFormatError(f"frame {sequence} must be an array or {{'0': array}}")
    if len(value) != CHANNEL_COUNT:
        raise JSONMeasurementFormatError(
            f"frame {sequence} has {len(value)} channels; expected {CHANNEL_COUNT}"
        )
    result: list[float] = []
    for channel, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise JSONMeasurementFormatError(f"frame {sequence}, channel {channel} is not numeric")
        number = float(item)
        if not math.isfinite(number):
            raise JSONMeasurementFormatError(f"frame {sequence}, channel {channel} is not finite")
        result.append(number)
    return tuple(result)


def _frame_rate(metadata: Mapping[str, Any], frame_count: int, fallback: float) -> tuple[float, str]:
    explicit = metadata.get("frame_rate_hz", metadata.get("fps"))
    if explicit is not None:
        return _positive_number(explicit, "metadata.frame_rate_hz"), "metadata"
    duration = metadata.get("duration_seconds")
    if duration is not None:
        return frame_count / _positive_number(duration, "metadata.duration_seconds"), "duration_estimate"
    return fallback, "configured_fallback"


def _positive_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JSONMeasurementFormatError(f"{field} must be a positive number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise JSONMeasurementFormatError(f"{field} must be a positive number")
    return number


def _optional_positive(value: Any) -> float | None:
    if value is None:
        return None
    return _positive_number(value, "metadata value")


def _optional_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise JSONMeasurementFormatError("electrode/channel counts must be positive integers")
    return value


def _param_number(parts: list[str], index: int) -> float | None:
    if len(parts) <= index:
        return None
    try:
        number = float(parts[index])
    except ValueError:
        return None
    return number if math.isfinite(number) and number > 0 else None


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise JSONMeasurementFormatError("metadata.recorded_at must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise JSONMeasurementFormatError("metadata.recorded_at must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise JSONMeasurementFormatError("metadata.recorded_at must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise JSONMeasurementFormatError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _convert_json_object(value: Any, context: str) -> Any:
    if isinstance(value, _JSONObject):
        result: dict[str, Any] = {}
        for key, item in value:
            if key in result:
                raise JSONMeasurementFormatError(f"duplicate key {key!r} in {context}")
            result[key] = _convert_json_object(item, f"field {key!r}")
        return result
    if isinstance(value, list):
        return [_convert_json_object(item, context) for item in value]
    return value
