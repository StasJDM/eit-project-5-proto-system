"""Versioned signal-processing and aeration calculations for EIT frames.

The MVP uses a fixed, normalized two-lung mask split into four
ventral-to-dorsal bands per lung.  Values are relative impedance units (AU):
no conversion to millilitres is implied.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math

import numpy as np

from ..domain import DataQuality, EITFrame, ROI_COUNT


DERIVATIVE_PEAK_DETECTOR = "derivative"
LEGACY_PEAK_DETECTOR = "legacy"
PEAK_DETECTORS = (DERIVATIVE_PEAK_DETECTOR, LEGACY_PEAK_DETECTOR)
ALGORITHM_VERSION = "eit-aeration-derivative-2.0.0"
LEGACY_ALGORITHM_VERSION = "eit-aeration-mvp-1.0.0"


@dataclass(frozen=True, slots=True)
class AerationAlgorithmParameters:
    """Parameters stored with every result through ``algorithm_version``."""

    sample_rate_hz: float = 25.0
    smoothing_samples: int = 5
    analysis_window_seconds: float = 30.0
    minimum_metric_seconds: float = 2.0
    minimum_complete_cycles: int = 3
    minimum_rr_bpm: float = 5.0
    maximum_rr_bpm: float = 60.0
    artifact_mad_multiplier: float = 30.0
    artifact_history_samples: int = 25
    peak_detection_method: str = DERIVATIVE_PEAK_DETECTOR
    derivative_window_seconds: float = 0.5
    derivative_dead_zone_multiplier: float = 3.0
    derivative_persistence_seconds: float = 0.12
    roi_count: int = ROI_COUNT
    version: str | None = None

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0 or not math.isfinite(self.sample_rate_hz):
            raise ValueError("sample_rate_hz must be positive and finite")
        if self.smoothing_samples <= 0:
            raise ValueError("smoothing_samples must be positive")
        if self.analysis_window_seconds <= 0:
            raise ValueError("analysis_window_seconds must be positive")
        if self.minimum_metric_seconds <= 0:
            raise ValueError("minimum_metric_seconds must be positive")
        if self.minimum_complete_cycles < 1:
            raise ValueError("minimum_complete_cycles must be positive")
        if not 0 < self.minimum_rr_bpm < self.maximum_rr_bpm:
            raise ValueError("respiratory-rate limits are invalid")
        if self.artifact_mad_multiplier <= 0 or self.artifact_history_samples < 3:
            raise ValueError("artifact parameters are invalid")
        if self.peak_detection_method not in PEAK_DETECTORS:
            raise ValueError("unsupported peak_detection_method")
        if self.derivative_window_seconds <= 0:
            raise ValueError("derivative_window_seconds must be positive")
        if self.derivative_dead_zone_multiplier <= 0:
            raise ValueError("derivative_dead_zone_multiplier must be positive")
        if self.derivative_persistence_seconds <= 0:
            raise ValueError("derivative_persistence_seconds must be positive")
        if not 2 <= self.roi_count <= 20 or self.roi_count % 2:
            raise ValueError("roi_count must be an even integer from 2 to 20")
        if self.version is None:
            object.__setattr__(
                self,
                "version",
                ALGORITHM_VERSION
                if self.peak_detection_method == DERIVATIVE_PEAK_DETECTOR
                else LEGACY_ALGORITHM_VERSION,
            )
        elif not self.version.strip():
            raise ValueError("version must not be blank")


@dataclass(frozen=True, slots=True)
class MetricAvailability:
    quality: DataQuality
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AerationResult:
    quality: DataQuality = DataQuality.UNAVAILABLE
    quality_reason: str | None = "insufficient_data"
    algorithm_version: str = ALGORITHM_VERSION
    respiratory_rate_bpm: float | None = None
    tvi_au: float | None = None
    eeli_au: float | None = None
    eili_au: float | None = None
    right_percent: float | None = None
    left_percent: float | None = None
    right_left_ratio: float | None = None
    ventral_dorsal_ratio: float | None = None
    roi_tvi_au: tuple[float | None, ...] = field(
        default_factory=lambda: (None,) * ROI_COUNT
    )
    roi_percent: tuple[float | None, ...] = field(
        default_factory=lambda: (None,) * ROI_COUNT
    )
    phase: float | None = None
    metric_statuses: tuple[tuple[str, MetricAvailability], ...] = ()
    parameters: AerationAlgorithmParameters = field(
        default_factory=AerationAlgorithmParameters
    )
    interval_start_seconds: float | None = None
    interval_end_seconds: float | None = None
    analyzed_sample_count: int = 0
    complete_cycle_count: int = 0
    selected_cycle_count: int | None = None

    @property
    def available(self) -> bool:
        return self.quality is not DataQuality.UNAVAILABLE

    def status_for(self, metric: str) -> MetricAvailability:
        return dict(self.metric_statuses).get(
            metric, MetricAvailability(self.quality, self.quality_reason)
        )


@dataclass(frozen=True, slots=True)
class ProcessedAerationSample:
    sequence_number: int
    time_seconds: float
    global_impedance: float
    roi_impedance: tuple[float, ...]
    quality: DataQuality


class AerationProcessor:
    """Incremental preprocessing followed by deterministic window analysis."""

    def __init__(
        self,
        parameters: AerationAlgorithmParameters | None = None,
        *,
        capacity: int = 2250,
    ) -> None:
        self.parameters = parameters or AerationAlgorithmParameters()
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._analysis_window_seconds = self.parameters.analysis_window_seconds
        self._analysis_cycle_count: int | None = None
        self.reset()

    def reset(self) -> None:
        width = self.parameters.smoothing_samples
        self._filter: tuple[deque[float], ...] = tuple(
            deque(maxlen=width) for _ in range(self.parameters.roi_count + 1)
        )
        self._times: deque[float] = deque(maxlen=self._capacity)
        self._global: deque[float] = deque(maxlen=self._capacity)
        self._rois: tuple[deque[float], ...] = tuple(
            deque(maxlen=self._capacity) for _ in range(self.parameters.roi_count)
        )
        self._recent_vectors: deque[np.ndarray] = deque(
            maxlen=self.parameters.artifact_history_samples + 1
        )
        self._last_quality = DataQuality.UNAVAILABLE
        self._quality_reason: str | None = "insufficient_data"

    @property
    def quality(self) -> DataQuality:
        return self._last_quality

    @property
    def quality_reason(self) -> str | None:
        return self._quality_reason

    def process(self, frame: EITFrame) -> ProcessedAerationSample | None:
        if frame.quality is DataQuality.UNAVAILABLE:
            self._last_quality = DataQuality.UNAVAILABLE
            self._quality_reason = "source_data_unavailable"
            return None
        global_value, roi_values = _derive_aeration_channels(
            frame, self.parameters.roi_count
        )
        vector = np.asarray((global_value, *roi_values), dtype=float)
        if self._is_artifact(vector):
            self._last_quality = DataQuality.DEGRADED
            self._quality_reason = "motion_or_signal_artifact"
            return None

        filtered: list[float] = []
        for history, value in zip(self._filter, vector):
            history.append(float(value))
            filtered.append(float(np.mean(history)))
        time_seconds = frame.sequence_number / self.parameters.sample_rate_hz
        self._times.append(time_seconds)
        self._global.append(filtered[0])
        for target, value in zip(self._rois, filtered[1:]):
            target.append(value)
        self._recent_vectors.append(vector)
        self._last_quality = frame.quality
        self._quality_reason = (
            "source_quality_degraded"
            if frame.quality is DataQuality.DEGRADED else None
        )
        return ProcessedAerationSample(
            sequence_number=frame.sequence_number,
            time_seconds=time_seconds,
            global_impedance=filtered[0],
            roi_impedance=tuple(filtered[1:]),
            quality=frame.quality,
        )

    def waveforms(self, window_seconds: float) -> dict[str, object]:
        count = max(1, int(window_seconds * self.parameters.sample_rate_hz))
        return {
            "time": np.asarray(tuple(self._times)[-count:], dtype=float),
            "global": np.asarray(tuple(self._global)[-count:], dtype=float),
            "rois": [
                np.asarray(tuple(values)[-count:], dtype=float)
                for values in self._rois
            ],
        }

    def configure_analysis(
        self, *, window_seconds: float, cycle_count: int | None = None
    ) -> None:
        """Select the latest time window and, optionally, its latest breaths."""
        if not math.isfinite(window_seconds) or window_seconds <= 0:
            raise ValueError("window_seconds must be positive and finite")
        if cycle_count is not None and cycle_count < 1:
            raise ValueError("cycle_count must be positive")
        self._analysis_window_seconds = float(window_seconds)
        self._analysis_cycle_count = cycle_count

    @property
    def analysis_selection(self) -> tuple[float, int | None]:
        return self._analysis_window_seconds, self._analysis_cycle_count

    def result(
        self,
        *,
        start_time_seconds: float | None = None,
        end_time_seconds: float | None = None,
        cycle_count: int | None = None,
    ) -> AerationResult:
        """Analyze a reproducible interval and optional latest complete cycles.

        With no explicit bounds, the configured rolling interval is used.  Explicit
        bounds make the same stored frame range independently re-analyzable.
        """
        explicit_interval = start_time_seconds is not None or end_time_seconds is not None
        waves = self.waveforms(
            self._capacity / self.parameters.sample_rate_hz
            if explicit_interval else self._analysis_window_seconds
        )
        times = waves["time"]
        global_values = waves["global"]
        roi_values = waves["rois"]
        selected_cycles = self._analysis_cycle_count if cycle_count is None else cycle_count
        if explicit_interval:
            if start_time_seconds is not None and not math.isfinite(start_time_seconds):
                raise ValueError("start_time_seconds must be finite")
            if end_time_seconds is not None and not math.isfinite(end_time_seconds):
                raise ValueError("end_time_seconds must be finite")
            if (
                start_time_seconds is not None
                and end_time_seconds is not None
                and start_time_seconds > end_time_seconds
            ):
                raise ValueError("analysis interval start must not exceed its end")
            mask = np.ones(times.size, dtype=bool)
            if start_time_seconds is not None:
                mask &= times >= start_time_seconds
            if end_time_seconds is not None:
                mask &= times <= end_time_seconds
            times = times[mask]
            global_values = global_values[mask]
            roi_values = [values[mask] for values in roi_values]

        if selected_cycles is not None:
            if selected_cycles < 1:
                raise ValueError("cycle_count must be positive")
            bounds = _latest_cycle_bounds(global_values, self.parameters, selected_cycles)
            if bounds is None:
                return _unavailable(
                    self.parameters,
                    "insufficient_complete_cycles",
                    time_values=times,
                    selected_cycle_count=selected_cycles,
                )
            start, stop = bounds
            times = times[start:stop]
            global_values = global_values[start:stop]
            roi_values = [values[start:stop] for values in roi_values]

        return calculate_aeration_metrics(
            global_values,
            roi_values,
            self.parameters,
            source_quality=self._last_quality,
            source_reason=self._quality_reason,
            time_values=times,
            selected_cycle_count=selected_cycles,
        )

    def _is_artifact(self, vector: np.ndarray) -> bool:
        history = self._recent_vectors
        if len(history) < self.parameters.artifact_history_samples:
            return False
        matrix = np.vstack(history)
        deltas = np.abs(np.diff(matrix, axis=0))
        median = np.median(deltas, axis=0)
        mad = np.median(np.abs(deltas - median), axis=0)
        scale = np.maximum(mad * 1.4826, np.maximum(np.abs(matrix[-1]), 1.0) * 1e-6)
        threshold = median + self.parameters.artifact_mad_multiplier * scale
        return bool(np.any(np.abs(vector - matrix[-1]) > threshold))


def calculate_aeration_metrics(
    global_values: np.ndarray,
    roi_values: list[np.ndarray],
    parameters: AerationAlgorithmParameters,
    *,
    source_quality: DataQuality = DataQuality.VALID,
    source_reason: str | None = None,
    time_values: np.ndarray | None = None,
    selected_cycle_count: int | None = None,
) -> AerationResult:
    """Calculate breath-based metrics, falling back to a marked time window."""

    global_values = np.asarray(global_values, dtype=float)
    times = (
        np.arange(global_values.size, dtype=float) / parameters.sample_rate_hz
        if time_values is None else np.asarray(time_values, dtype=float)
    )
    roi_count = parameters.roi_count
    if len(roi_values) != roi_count:
        raise ValueError(f"exactly {roi_count} ROI channels are required")
    if times.ndim != 1 or times.size != global_values.size:
        raise ValueError("time_values must match the global channel")
    minimum = max(2, round(
        parameters.minimum_metric_seconds * parameters.sample_rate_hz
    ))
    if global_values.size < minimum or any(len(values) != global_values.size for values in roi_values):
        return _unavailable(
            parameters, source_reason or "insufficient_data", time_values=times,
            selected_cycle_count=selected_cycle_count,
        )
    if not np.all(np.isfinite(global_values)) or any(
        not np.all(np.isfinite(values)) for values in roi_values
    ):
        return _unavailable(
            parameters, "non_finite_data", time_values=times,
            selected_cycle_count=selected_cycle_count,
        )
    if not np.all(np.isfinite(times)) or np.any(np.diff(times) < 0):
        return _unavailable(
            parameters, "invalid_time_axis", time_values=times,
            selected_cycle_count=selected_cycle_count,
        )

    detection_values = _breathing_detection_signal(global_values, parameters)
    maxima, minima = _breath_turning_points(detection_values, parameters)
    min_distance = max(1, round(
        parameters.sample_rate_hz * 60.0 / parameters.maximum_rr_bpm
    ))
    maxima = _separate_peaks(maxima, detection_values, min_distance)
    intervals = (
        np.diff(times[maxima])
        if maxima.size >= 2 else np.asarray([], dtype=float)
    )
    maximum_interval = 60.0 / parameters.minimum_rr_bpm
    minimum_interval = 60.0 / parameters.maximum_rr_bpm
    valid_intervals = intervals[
        (intervals >= minimum_interval) & (intervals <= maximum_interval)
    ]
    cycle_count = int(valid_intervals.size)
    rr = None
    if cycle_count >= parameters.minimum_complete_cycles:
        selected = valid_intervals[-4:]
        # Median is stable when one noisy cycle peak is missed and therefore
        # appears as a doubled interval.
        rr = float(60.0 / np.median(selected))

    boundary_fallback = False
    if parameters.peak_detection_method == DERIVATIVE_PEAK_DETECTOR:
        pair = _latest_derivative_breath(maxima, minima)
        if pair is not None:
            expiration_index, inspiration_index = pair
        else:
            # Preserve useful amplitudes on short windows, but expose that the
            # derivative state machine could not confirm a complete breath.
            boundary_fallback = True
            expiration_index = int(np.argmin(global_values))
            inspiration_index = int(np.argmax(global_values))
    # Legacy behaviour: use extrema inside the latest maximum-to-maximum span.
    elif maxima.size >= 2:
        start = int(maxima[-2])
        stop = int(maxima[-1]) + 1
        segment = global_values[start:stop]
        exp_offset = int(np.argmin(segment))
        insp_offset = int(np.argmax(segment))
        expiration_index = start + exp_offset
        inspiration_index = start + insp_offset
        if inspiration_index <= expiration_index:
            expiration_index = int(np.argmin(global_values[max(0, stop - round(5 * parameters.sample_rate_hz)):stop])) + max(0, stop - round(5 * parameters.sample_rate_hz))
            inspiration_index = int(np.argmax(global_values[expiration_index:stop])) + expiration_index
    else:
        expiration_index = int(np.argmin(global_values))
        inspiration_index = int(np.argmax(global_values))

    eeli = float(global_values[expiration_index])
    eili = float(global_values[inspiration_index])
    if eili < eeli:
        eeli, eili = eili, eeli
        expiration_index, inspiration_index = inspiration_index, expiration_index
    tvi = eili - eeli
    noise = float(np.median(np.abs(np.diff(global_values) - np.median(np.diff(global_values)))))
    minimum_amplitude = max(1e-9, noise * 6.0)
    if tvi <= minimum_amplitude:
        return _unavailable(
            parameters, "no_detectable_breathing", time_values=times,
            complete_cycle_count=cycle_count,
            selected_cycle_count=selected_cycle_count,
        )

    roi_tvi = np.asarray([
        max(0.0, float(values[inspiration_index] - values[expiration_index]))
        for values in roi_values
    ])
    roi_total = float(roi_tvi.sum())
    if roi_total <= 1e-12:
        return _unavailable(
            parameters, "regional_signal_unavailable", time_values=times,
            complete_cycle_count=cycle_count,
            selected_cycle_count=selected_cycle_count,
        )
    roi_percent = roi_tvi / roi_total * 100.0
    bands_per_lung = roi_count // 2
    right = float(roi_percent[:bands_per_lung].sum())
    left = float(roi_percent[bands_per_lung:].sum())
    ventral_weights, dorsal_weights = _ventral_dorsal_weights(bands_per_lung)
    ventral = float(sum(
        roi_percent[offset + band] * ventral_weights[band]
        for offset in (0, bands_per_lung)
        for band in range(bands_per_lung)
    ))
    dorsal = float(sum(
        roi_percent[offset + band] * dorsal_weights[band]
        for offset in (0, bands_per_lung)
        for band in range(bands_per_lung)
    ))
    phase = float(np.clip((global_values[-1] - eeli) / max(tvi, 1e-12), 0.0, 1.0))

    fallback = rr is None or boundary_fallback
    quality = source_quality
    reason = source_reason
    if quality is DataQuality.UNAVAILABLE:
        return _unavailable(
            parameters, reason or "source_data_unavailable", time_values=times,
            complete_cycle_count=cycle_count,
            selected_cycle_count=selected_cycle_count,
        )
    if fallback and quality is DataQuality.VALID:
        quality = DataQuality.DEGRADED
        reason = "time_window_fallback"
    base_status = MetricAvailability(quality, reason)
    statuses = {name: base_status for name in _metric_names(roi_count)}
    if rr is None:
        statuses["rr"] = MetricAvailability(
            DataQuality.UNAVAILABLE, "insufficient_complete_cycles"
        )
    if left <= 1e-12:
        statuses["rl_ratio"] = MetricAvailability(
            DataQuality.UNAVAILABLE, "left_region_zero"
        )
    if dorsal <= 1e-12:
        statuses["vd_ratio"] = MetricAvailability(
            DataQuality.UNAVAILABLE, "dorsal_region_zero"
        )
    return AerationResult(
        quality=quality,
        quality_reason=reason,
        algorithm_version=str(parameters.version),
        respiratory_rate_bpm=rr,
        tvi_au=tvi,
        eeli_au=eeli,
        eili_au=eili,
        right_percent=right,
        left_percent=left,
        right_left_ratio=right / left if left > 1e-12 else None,
        ventral_dorsal_ratio=ventral / dorsal if dorsal > 1e-12 else None,
        roi_tvi_au=tuple(float(value) for value in roi_tvi),
        roi_percent=tuple(float(value) for value in roi_percent),
        phase=phase,
        metric_statuses=tuple(statuses.items()),
        parameters=parameters,
        interval_start_seconds=float(times[0]) if times.size else None,
        interval_end_seconds=float(times[-1]) if times.size else None,
        analyzed_sample_count=int(times.size),
        complete_cycle_count=cycle_count,
        selected_cycle_count=selected_cycle_count,
    )


def _metric_names(roi_count: int) -> tuple[str, ...]:
    return (
        "rr", "tvi", "eeli", "eili", "r_pct", "l_pct", "rl_ratio", "vd_ratio",
        *(f"roi_{index}" for index in range(1, roi_count + 1)),
    )


def _unavailable(
    parameters: AerationAlgorithmParameters,
    reason: str,
    *,
    time_values: np.ndarray | None = None,
    complete_cycle_count: int = 0,
    selected_cycle_count: int | None = None,
) -> AerationResult:
    times = np.asarray(time_values if time_values is not None else (), dtype=float)
    status = MetricAvailability(DataQuality.UNAVAILABLE, reason)
    return AerationResult(
        quality=DataQuality.UNAVAILABLE,
        quality_reason=reason,
        algorithm_version=str(parameters.version),
        roi_tvi_au=(None,) * parameters.roi_count,
        roi_percent=(None,) * parameters.roi_count,
        metric_statuses=tuple((name, status) for name in _metric_names(parameters.roi_count)),
        parameters=parameters,
        interval_start_seconds=float(times[0]) if times.size else None,
        interval_end_seconds=float(times[-1]) if times.size else None,
        analyzed_sample_count=int(times.size),
        complete_cycle_count=complete_cycle_count,
        selected_cycle_count=selected_cycle_count,
    )


def _latest_cycle_bounds(
    values: np.ndarray,
    parameters: AerationAlgorithmParameters,
    cycle_count: int,
) -> tuple[int, int] | None:
    """Return a half-open slice containing the latest contiguous valid cycles."""
    detection_values = _breathing_detection_signal(values, parameters)
    maxima, _ = _breath_turning_points(detection_values, parameters)
    if maxima.size < cycle_count + 1:
        return None
    minimum = parameters.sample_rate_hz * 60.0 / parameters.maximum_rr_bpm
    maximum = parameters.sample_rate_hz * 60.0 / parameters.minimum_rr_bpm
    for stop_position in range(maxima.size - 1, cycle_count - 1, -1):
        group = maxima[stop_position - cycle_count:stop_position + 1]
        intervals = np.diff(group)
        if np.all((intervals >= minimum) & (intervals <= maximum)):
            edge = max(2, round(parameters.sample_rate_hz * 0.5))
            return (
                max(0, int(group[0]) - edge),
                min(values.size, int(group[-1]) + edge + 1),
            )
    return None


def _breathing_detection_signal(
    values: np.ndarray, parameters: AerationAlgorithmParameters
) -> np.ndarray:
    """Suppress sample jitter without shifting detected breath boundaries."""
    width = max(3, round(parameters.sample_rate_hz * 0.5))
    if width % 2 == 0:
        width += 1
    if values.size < width:
        return values
    padding = width // 2
    padded = np.pad(values, (padding, padding), mode="edge")
    return np.convolve(padded, np.ones(width) / width, mode="valid")


def _breath_turning_points(
    values: np.ndarray, parameters: AerationAlgorithmParameters
) -> tuple[np.ndarray, np.ndarray]:
    """Return end-inspiration maxima and end-expiration minima."""
    distance = max(1, round(
        parameters.sample_rate_hz * 60.0 / parameters.maximum_rr_bpm
    ))
    if parameters.peak_detection_method == LEGACY_PEAK_DETECTOR:
        maxima = _turning_points(values, maxima=True)
        minima = _turning_points(values, maxima=False)
    else:
        maxima, minima = _derivative_turning_points(values, parameters)
    return (
        _separate_peaks(maxima, values, distance),
        _separate_peaks(minima, -values, distance),
    )


def _derivative_turning_points(
    values: np.ndarray, parameters: AerationAlgorithmParameters
) -> tuple[np.ndarray, np.ndarray]:
    """Detect persistent derivative sign changes with an adaptive dead zone.

    A local linear fit estimates dZ/dt in a centred time interval.  The dead
    zone is derived from the robust variation of adjacent slope estimates and
    capped relative to the useful slope range so that clean slow breaths are
    not suppressed.  A positive-to-negative transition marks end inspiration;
    the opposite transition marks end expiration.
    """
    if values.size < 3:
        empty = np.asarray([], dtype=int)
        return empty, empty
    width = max(3, round(
        parameters.derivative_window_seconds * parameters.sample_rate_hz
    ))
    if width % 2 == 0:
        width += 1
    width = min(width, values.size if values.size % 2 else values.size - 1)
    if width < 3:
        empty = np.asarray([], dtype=int)
        return empty, empty
    half = width // 2
    x = np.arange(-half, half + 1, dtype=float) / parameters.sample_rate_hz
    kernel = x / float(np.dot(x, x))
    padded = np.pad(values, (half, half), mode="edge")
    slopes = np.convolve(padded, kernel[::-1], mode="valid")

    slope_delta = np.diff(slopes)
    delta_median = float(np.median(slope_delta))
    delta_mad = float(np.median(np.abs(slope_delta - delta_median)))
    noise = 1.4826 * delta_mad / math.sqrt(2.0)
    useful_slope = float(np.percentile(np.abs(slopes), 90))
    epsilon = max(
        1e-12,
        min(
            noise * parameters.derivative_dead_zone_multiplier,
            useful_slope * 0.20,
        ),
    )
    signs = np.where(slopes > epsilon, 1, np.where(slopes < -epsilon, -1, 0))
    persistence = max(1, round(
        parameters.derivative_persistence_seconds * parameters.sample_rate_hz
    ))

    maxima: list[int] = []
    minima: list[int] = []
    state = 0
    last_state_index = 0
    index = 0
    while index < signs.size:
        sign = int(signs[index])
        if sign == 0:
            index += 1
            continue
        stop = min(signs.size, index + persistence)
        if stop - index < persistence or not np.all(signs[index:stop] == sign):
            index += 1
            continue
        if state == 0:
            state = sign
        elif sign != state:
            span_start = min(last_state_index, index)
            span = np.abs(slopes[span_start:index + 1])
            minimum = float(np.min(span))
            closest = np.flatnonzero(np.isclose(span, minimum, rtol=0.0, atol=1e-15))
            candidate = span_start + int(round(float(np.mean(closest))))
            (maxima if state > 0 else minima).append(candidate)
            state = sign
        last_state_index = stop - 1
        index = stop
    return np.asarray(maxima, dtype=int), np.asarray(minima, dtype=int)


def _latest_derivative_breath(
    maxima: np.ndarray, minima: np.ndarray
) -> tuple[int, int] | None:
    """Pair the latest confirmed inspiration with its preceding expiration."""
    if maxima.size == 0 or minima.size == 0:
        return None
    inspiration = int(maxima[-1])
    lower_bound = int(maxima[-2]) if maxima.size >= 2 else -1
    candidates = minima[(minima > lower_bound) & (minima < inspiration)]
    if candidates.size == 0:
        return None
    return int(candidates[-1]), inspiration


def _derive_aeration_channels(
    frame: EITFrame, roi_count: int
) -> tuple[float, tuple[float, ...]]:
    image = np.asarray(frame.reconstructed_delta_z, dtype=float)
    # Tiny diagnostic maps use the versioned eight-channel frame as a
    # compatibility source and deterministically resample it to the requested
    # number of regions.
    if image.ndim != 2 or min(image.shape) < 8:
        values = _resample_roi_values(frame.roi_impedance, roi_count)
        return float(frame.global_impedance), values
    masks = _lung_roi_masks(image.shape, roi_count)
    roi_values = tuple(float(image[mask].sum()) for mask in masks)
    return float(sum(roi_values)), roi_values


def _lung_roi_masks(
    shape: tuple[int, int], roi_count: int
) -> tuple[np.ndarray, ...]:
    height, width = shape
    y, x = np.mgrid[-1.0:1.0:complex(height), -1.0:1.0:complex(width)]
    right = ((x + 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0
    left = ((x - 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0
    bands_per_lung = roi_count // 2
    edges = np.linspace(-0.62, 0.62, bands_per_lung + 1)
    result: list[np.ndarray] = []
    for lung in (right, left):
        for index in range(bands_per_lung):
            upper = (
                y <= edges[index + 1]
                if index == bands_per_lung - 1
                else y < edges[index + 1]
            )
            result.append(lung & (y >= edges[index]) & upper)
    return tuple(result)


def _resample_roi_values(
    source: tuple[float, ...], roi_count: int
) -> tuple[float, ...]:
    """Preserve each lung total while changing its ventral/dorsal resolution."""
    source_bands = len(source) // 2
    target_bands = roi_count // 2
    result: list[float] = []
    for offset in (0, source_bands):
        values = np.asarray(source[offset:offset + source_bands], dtype=float)
        source_edges = np.linspace(0.0, 1.0, source_bands + 1)
        target_edges = np.linspace(0.0, 1.0, target_bands + 1)
        for target in range(target_bands):
            total = 0.0
            for index, value in enumerate(values):
                overlap = max(
                    0.0,
                    min(target_edges[target + 1], source_edges[index + 1])
                    - max(target_edges[target], source_edges[index]),
                )
                total += float(value) * overlap * source_bands
            result.append(total)
    return tuple(result)


def _ventral_dorsal_weights(
    bands_per_lung: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Split a centre band equally when a lung has an odd band count."""
    centers = (np.arange(bands_per_lung, dtype=float) + 0.5) / bands_per_lung
    ventral = np.where(centers < 0.5, 1.0, np.where(centers == 0.5, 0.5, 0.0))
    return ventral, 1.0 - ventral


def _turning_points(values: np.ndarray, *, maxima: bool) -> np.ndarray:
    if values.size < 3:
        return np.asarray([], dtype=int)
    left = values[1:-1] - values[:-2]
    right = values[2:] - values[1:-1]
    mask = (left > 0) & (right <= 0) if maxima else (left < 0) & (right >= 0)
    return np.flatnonzero(mask) + 1


def _separate_peaks(indices: np.ndarray, values: np.ndarray, distance: int) -> np.ndarray:
    if indices.size == 0:
        return indices
    selected: list[int] = []
    for index in indices:
        index = int(index)
        if not selected or index - selected[-1] >= distance:
            selected.append(index)
        elif values[index] > values[selected[-1]]:
            selected[-1] = index
    amplitude = float(np.ptp(values))
    if amplitude <= 1e-12:
        return np.asarray([], dtype=int)
    floor = float(np.min(values) + amplitude * 0.35)
    return np.asarray([index for index in selected if values[index] >= floor], dtype=int)
