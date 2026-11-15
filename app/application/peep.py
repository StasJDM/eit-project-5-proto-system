"""PEEP-oriented ventilation-distribution indices from EIT image sequences.

The terminology and default threshold follow LuMon User's Guide section 9.10:
RTS is normalized to the largest pixel tidal change, Silent Spaces have
RTS <= 10%, and CoV is the RTS-weighted geometrical centre of the Lung ROI.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math

import numpy as np


PEEP_ALGORITHM_VERSION = "eit-peep-lumon-9.10-1.0.0"


@dataclass(frozen=True, slots=True)
class PeepResult:
    available: bool = False
    reason: str | None = "insufficient_data"
    algorithm_version: str = PEEP_ALGORITHM_VERSION
    rts_map: tuple[tuple[float, ...], ...] | None = None
    lung_mask: tuple[tuple[bool, ...], ...] | None = None
    silent_mask: tuple[tuple[bool, ...], ...] | None = None
    cov_x_percent: float | None = None
    cov_y_percent: float | None = None
    cov_v_percent: float | None = None
    cov_h_percent: float | None = None
    horizon_line: tuple[tuple[float, float], tuple[float, float]] | None = None
    fls_percent: float | None = None
    dss_percent: float | None = None
    nss_percent: float | None = None
    silent_threshold_percent: float = 10.0
    analysis_interval_seconds: float = 15.0
    gravity_angle_degrees: float = 0.0
    analyzed_sample_count: int = 0


class PeepProcessor:
    """Keep a bounded image history and calculate section 9.10 indices."""

    def __init__(
        self,
        *,
        sample_rate_hz: float = 25.0,
        capacity: int = 3000,
        silent_threshold_percent: float = 10.0,
        analysis_interval_seconds: float = 15.0,
        gravity_angle_degrees: float = 0.0,
    ) -> None:
        if sample_rate_hz <= 0 or capacity < 2:
            raise ValueError("invalid PEEP processor capacity or sample rate")
        self.sample_rate_hz = float(sample_rate_hz)
        self._capacity = int(capacity)
        self._maps: deque[np.ndarray] = deque(maxlen=capacity)
        self._global: deque[float] = deque(maxlen=capacity)
        self.configure(
            silent_threshold_percent=silent_threshold_percent,
            analysis_interval_seconds=analysis_interval_seconds,
            gravity_angle_degrees=gravity_angle_degrees,
        )

    def configure(
        self,
        *,
        silent_threshold_percent: float,
        analysis_interval_seconds: float,
        gravity_angle_degrees: float,
    ) -> None:
        if not math.isfinite(silent_threshold_percent) or not 0 <= silent_threshold_percent < 100:
            raise ValueError("silent_threshold_percent must be from 0 to below 100")
        if not math.isfinite(analysis_interval_seconds) or analysis_interval_seconds <= 0:
            raise ValueError("analysis_interval_seconds must be positive")
        if not math.isfinite(gravity_angle_degrees) or not -180 <= gravity_angle_degrees <= 180:
            raise ValueError("gravity_angle_degrees must be from -180 to 180")
        self.silent_threshold_percent = float(silent_threshold_percent)
        self.analysis_interval_seconds = float(analysis_interval_seconds)
        self.gravity_angle_degrees = float(gravity_angle_degrees)

    def reset(self) -> None:
        self._maps.clear()
        self._global.clear()

    def process(self, reconstructed_map, global_impedance: float) -> None:
        image = np.asarray(reconstructed_map, dtype=float)
        if image.ndim != 2 or min(image.shape) < 8 or not np.all(np.isfinite(image)):
            return
        if self._maps and image.shape != self._maps[-1].shape:
            self.reset()
        self._maps.append(image.copy())
        self._global.append(float(global_impedance))

    def result(self) -> PeepResult:
        count = min(
            len(self._maps),
            max(2, int(round(self.analysis_interval_seconds * self.sample_rate_hz))),
        )
        common = dict(
            silent_threshold_percent=self.silent_threshold_percent,
            analysis_interval_seconds=self.analysis_interval_seconds,
            gravity_angle_degrees=self.gravity_angle_degrees,
            analyzed_sample_count=count,
        )
        if count < 2:
            return PeepResult(**common)
        maps = np.stack(tuple(self._maps)[-count:])
        global_values = np.asarray(tuple(self._global)[-count:], dtype=float)
        low = int(np.argmin(global_values))
        high = int(np.argmax(global_values))
        tidal_change = np.abs(maps[high] - maps[low])
        return calculate_peep_metrics(
            tidal_change,
            silent_threshold_percent=self.silent_threshold_percent,
            analysis_interval_seconds=self.analysis_interval_seconds,
            gravity_angle_degrees=self.gravity_angle_degrees,
            analyzed_sample_count=count,
        )


def calculate_peep_metrics(
    tidal_change,
    *,
    silent_threshold_percent: float = 10.0,
    analysis_interval_seconds: float = 15.0,
    gravity_angle_degrees: float = 0.0,
    analyzed_sample_count: int = 0,
) -> PeepResult:
    """Calculate RTS, CoV, HoV and silent/functional lung-space percentages."""
    image = np.asarray(tidal_change, dtype=float)
    common = dict(
        silent_threshold_percent=float(silent_threshold_percent),
        analysis_interval_seconds=float(analysis_interval_seconds),
        gravity_angle_degrees=float(gravity_angle_degrees),
        analyzed_sample_count=int(analyzed_sample_count),
    )
    if image.ndim != 2 or min(image.shape) < 8 or not np.all(np.isfinite(image)):
        return PeepResult(reason="invalid_reconstruction_map", **common)
    lung = _lung_mask(image.shape)
    values = np.maximum(image, 0.0)
    maximum = float(np.max(values[lung]))
    if maximum <= 1e-12:
        return PeepResult(reason="no_tidal_change", **common)
    rts = np.zeros_like(values)
    rts[lung] = values[lung] / maximum * 100.0
    weights = rts[lung]
    rows, columns = np.nonzero(lung)
    total_weight = float(np.sum(weights))
    cov_x = float(np.sum(columns * weights) / total_weight)
    cov_y = float(np.sum(rows * weights) / total_weight)

    theta = math.radians(gravity_angle_degrees)
    gravity = np.asarray((math.sin(theta), math.cos(theta)), dtype=float)  # x, y
    horizontal = np.asarray((math.cos(theta), -math.sin(theta)), dtype=float)
    points = np.column_stack((columns.astype(float), rows.astype(float)))
    cov = np.asarray((cov_x, cov_y), dtype=float)
    v_projection = points @ gravity
    h_projection = points @ horizontal
    cov_v = _percent_on_axis(float(cov @ gravity), v_projection)
    cov_h = _percent_on_axis(float(cov @ horizontal), h_projection)

    signed = (points - cov) @ gravity
    silent_values = weights <= silent_threshold_percent
    dependent = signed >= 0.0
    pixel_count = int(np.count_nonzero(lung))
    dss = float(np.count_nonzero(silent_values & dependent) / pixel_count * 100.0)
    nss = float(np.count_nonzero(silent_values & ~dependent) / pixel_count * 100.0)
    fls = float(np.count_nonzero(~silent_values) / pixel_count * 100.0)

    silent = np.zeros_like(lung)
    silent[rows, columns] = silent_values
    horizon = _line_through_roi(cov, horizontal, points)
    return PeepResult(
        available=True,
        reason=None,
        rts_map=_tuple_map(rts),
        lung_mask=tuple(tuple(bool(value) for value in row) for row in lung),
        silent_mask=tuple(tuple(bool(value) for value in row) for row in silent),
        cov_x_percent=float(cov_x / max(1, image.shape[1] - 1) * 100.0),
        cov_y_percent=float(cov_y / max(1, image.shape[0] - 1) * 100.0),
        cov_v_percent=cov_v,
        cov_h_percent=cov_h,
        horizon_line=horizon,
        fls_percent=fls,
        dss_percent=dss,
        nss_percent=nss,
        **common,
    )


def _lung_mask(shape: tuple[int, int]) -> np.ndarray:
    height, width = shape
    y, x = np.mgrid[-1.0:1.0:complex(height), -1.0:1.0:complex(width)]
    right = ((x + 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0
    left = ((x - 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0
    return right | left


def _percent_on_axis(value: float, projections: np.ndarray) -> float:
    low, high = float(np.min(projections)), float(np.max(projections))
    return (value - low) / max(1e-12, high - low) * 100.0


def _line_through_roi(
    origin: np.ndarray, direction: np.ndarray, points: np.ndarray
) -> tuple[tuple[float, float], tuple[float, float]]:
    offsets = (points - origin) @ direction
    start = origin + direction * float(np.min(offsets))
    end = origin + direction * float(np.max(offsets))
    return ((float(start[0]), float(start[1])), (float(end[0]), float(end[1])))


def _tuple_map(values: np.ndarray) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(value) for value in row) for row in values)
