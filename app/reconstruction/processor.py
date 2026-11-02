"""Streaming reconstruction of raw 16-electrode EIT measurements.

The processor performs time-difference EIT.  It builds a robust reference from
the first second of data, applies a precomputed GREIT operator backed by a 2-D
FEM complete-electrode model, and exposes an impedance-oriented 64x64 map to
the existing aeration pipeline.

The bundled adjacent 16x13 channel order and circular adult geometry are an
explicit research hypothesis until a device profile confirms them.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING

import numpy as np

from ..domain import AcquisitionSettings, DataQuality, EITFrame
from .forward import CompleteElectrodeModel
from .geometry import geometry_profile
from .greit import GreitConfig, GreitReconstructor
from .mesh import MeshDensity, generate_mesh
from .protocol import MeasurementProtocol

if TYPE_CHECKING:
    from ..data_sources.json_contract import RawMeasurementFrame


ADJACENT_16_PROTOCOL_ID = "adjacent-16x13-hypothesis-v1"


RECONSTRUCTION_ALGORITHM_VERSION = "eit-greit-fem-research-1.2.0"


@dataclass(frozen=True, slots=True)
class ReconstructionDiagnostics:
    ready: bool
    reference_frame_count: int
    active_channel_count: int
    protocol_id: str = ADJACENT_16_PROTOCOL_ID
    geometry_profile_id: str = "adult-circle-v1"
    algorithm_version: str = RECONSTRUCTION_ALGORITHM_VERSION
    assumptions_confirmed: bool = False
    reason: str = "unconfirmed_protocol_and_geometry"


class RawFrameReconstructor:
    """Convert raw 208-channel frames to synchronized reconstructed EIT frames."""

    def __init__(
        self,
        settings: AcquisitionSettings,
        *,
        reference_seconds: float = 1.0,
        pixel_size: int = 64,
        mesh_density: MeshDensity = MeshDensity.LOW,
    ) -> None:
        if reference_seconds <= 0:
            raise ValueError("reference_seconds must be positive")
        self._settings = settings
        self._reference_target = max(
            3, round(reference_seconds * settings.sample_rate_hz)
        )
        self._reference_samples: list[np.ndarray] = []
        self._reference: np.ndarray | None = None
        self._channel_weights = np.ones(208, dtype=float)
        self._absolute_center: float | None = None
        self._absolute_scale: float | None = None
        self._lock = RLock()

        self._protocol = MeasurementProtocol.adjacent_16_hypothesis(
            electrode_order=settings.electrode_order,
            measurement_sequence=settings.measurement_sequence,
        )
        profile = geometry_profile("adult")
        mesh = generate_mesh(profile, self._protocol, mesh_density)
        model = CompleteElectrodeModel(
            mesh, profile, self._protocol
        )
        current_amperes = settings.injection_current_ma / 1000.0
        self._model = model
        self._current_amperes = current_amperes
        self._background_conductivity = profile.background_conductivity_s_m
        self._homogeneous_measurements = model.solve(
            self._background_conductivity,
            current_amperes=current_amperes,
        ).measurements
        self._reconstructor = GreitReconstructor(
            model,
            GreitConfig(
                regularization_lambda=0.02,
                noise_figure=0.5,
                pixel_size=pixel_size,
                current_amperes=current_amperes,
            ),
        )
        self._diagnostics = ReconstructionDiagnostics(
            ready=False,
            reference_frame_count=0,
            active_channel_count=208,
            protocol_id=self._protocol.protocol_id,
        )

    @property
    def diagnostics(self) -> ReconstructionDiagnostics:
        with self._lock:
            return self._diagnostics

    def reset(self) -> None:
        with self._lock:
            self._reference_samples.clear()
            self._reference = None
            self._channel_weights = np.ones(208, dtype=float)
            self._absolute_center = None
            self._absolute_scale = None
            self._diagnostics = ReconstructionDiagnostics(
                ready=False,
                reference_frame_count=0,
                active_channel_count=208,
                protocol_id=self._protocol.protocol_id,
            )

    def prime_reference(
        self,
        frames: list[RawMeasurementFrame] | tuple[RawMeasurementFrame, ...],
    ) -> None:
        """Install a deterministic reference, used by seekable JSON recordings."""
        if len(frames) < 3:
            raise ValueError("at least three frames are required for a reference")
        samples = [
            np.asarray(frame.channel_values, dtype=float).copy() for frame in frames
        ]
        with self._lock:
            self._reference_samples = samples
            self._prepare_reference()

    def process(self, frame: RawMeasurementFrame) -> EITFrame | None:
        if frame.protocol_id != ADJACENT_16_PROTOCOL_ID:
            raise ValueError(
                f"unsupported reconstruction protocol: {frame.protocol_id!r}"
            )
        values = np.asarray(frame.channel_values, dtype=float)
        with self._lock:
            if self._reference is None:
                self._reference_samples.append(values.copy())
                if len(self._reference_samples) < self._reference_target:
                    self._diagnostics = ReconstructionDiagnostics(
                        ready=False,
                        reference_frame_count=len(self._reference_samples),
                        active_channel_count=208,
                        protocol_id=self._protocol.protocol_id,
                        reason="collecting_reference",
                    )
                    return None
                self._prepare_reference()

            delta_v = values - self._reference
            result = self._reconstructor.reconstruct(
                delta_v,
                channel_weights=self._channel_weights,
            )
            # Air filling raises impedance and lowers conductivity.  The domain
            # contract stores delta-Z-like ventilation activity, hence -delta sigma.
            delta_z = -np.nan_to_num(
                result.image, nan=0.0, posinf=0.0, neginf=0.0
            )
            absolute_conductivity = self._reconstruct_absolute_conductivity(values)
            global_value, roi_values = _map_channels(delta_z)
            return EITFrame(
                sequence_number=frame.sequence_number,
                timestamp_utc=frame.timestamp_utc,
                belt_index=frame.belt_index,
                global_impedance=global_value,
                roi_impedance=roi_values,
                reconstructed_delta_z=tuple(
                    tuple(float(value) for value in row) for row in delta_z
                ),
                absolute_conductivity=tuple(
                    tuple(float(value) for value in row)
                    for row in absolute_conductivity
                ),
                # The numerical calculation is real, but its device assumptions
                # are not confirmed; never expose it as clinically valid data.
                quality=(
                    DataQuality.DEGRADED
                    if frame.quality is DataQuality.VALID
                    else frame.quality
                ),
                simulated=frame.simulated,
            )

    def _reconstruct_absolute_conductivity(self, values: np.ndarray) -> np.ndarray:
        """Estimate a positive spatial conductivity map without a temporal baseline.

        The source files do not declare voltage units or polarity.  We therefore
        fit their global gain and sign to a homogeneous CEM prediction, reconstruct
        the remaining spatial contrast, and report conductivity relative to its
        thorax median.  The result is dimensionless and must not be interpreted as
        calibrated S/m.
        """

        model_values = self._homogeneous_measurements
        candidates = (
            values,
            np.abs(values) * np.where(model_values < 0.0, -1.0, 1.0),
        )
        best_scaled: np.ndarray | None = None
        best_error = float("inf")
        for candidate in candidates:
            energy = float(np.dot(candidate, candidate))
            if energy <= np.finfo(float).tiny:
                continue
            gain = float(np.dot(candidate, model_values) / energy)
            scaled = candidate * gain
            error = float(np.linalg.norm(scaled - model_values))
            if error < best_error:
                best_scaled = scaled
                best_error = error
        if best_scaled is None:
            size = self._reconstructor.config.pixel_size
            return np.zeros((size, size), dtype=float)

        static_result = self._reconstructor.reconstruct(
            best_scaled - model_values,
            reference_conductivity=self._background_conductivity,
            channel_weights=self._channel_weights,
        )
        delta_sigma = static_result.image
        inside = np.isfinite(delta_sigma)
        relative = np.zeros_like(delta_sigma, dtype=float)
        if not np.any(inside):
            return relative
        if self._absolute_center is None:
            self._absolute_center = float(np.median(delta_sigma[inside]))
        centered = delta_sigma[inside] - self._absolute_center
        if self._absolute_scale is None:
            candidate_scale = float(np.quantile(np.abs(centered), 0.95))
            if candidate_scale > np.finfo(float).tiny:
                self._absolute_scale = candidate_scale
        scale = self._absolute_scale or 0.0
        if scale <= np.finfo(float).tiny:
            relative[inside] = 1.0
            return relative
        # Exponential parameterization enforces positive conductivity.  Values
        # are relative to the spatial median (1.0), not physical S/m.
        relative[inside] = np.exp(np.clip(centered / scale, -1.5, 1.5))
        return relative

    def _prepare_reference(self) -> None:
        samples = np.vstack(self._reference_samples)
        self._reference = np.median(samples, axis=0)
        deviations = np.median(
            np.abs(samples - self._reference[None, :]), axis=0
        )
        finite_positive = deviations[np.isfinite(deviations) & (deviations > 0)]
        typical = float(np.median(finite_positive)) if finite_positive.size else 0.0
        if typical > 0:
            noisy = deviations > typical * 8.0
            # Zeroing a channel weight excludes it from the inverse solution.
            self._channel_weights = (~noisy).astype(float)
        active = int(np.count_nonzero(self._channel_weights))
        if active < 104:
            # Too few measurements for a stable 16-electrode reconstruction.
            raise ValueError(
                f"insufficient usable EIT channels for reconstruction: {active}/208"
            )
        self._diagnostics = ReconstructionDiagnostics(
            ready=True,
            reference_frame_count=len(self._reference_samples),
            active_channel_count=active,
            protocol_id=self._protocol.protocol_id,
        )
        # Lock the absolute-map normalization to the deterministic reference,
        # so seeking or frame-to-frame changes cannot rescale the colours.
        self._absolute_center = None
        self._absolute_scale = None
        self._reconstruct_absolute_conductivity(self._reference)


def _map_channels(image: np.ndarray) -> tuple[float, tuple[float, ...]]:
    height, width = image.shape
    y, x = np.mgrid[-1.0:1.0:complex(height), -1.0:1.0:complex(width)]
    right = ((x + 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0
    left = ((x - 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0
    edges = np.linspace(-0.62, 0.62, 5)
    values: list[float] = []
    for lung in (right, left):
        for index in range(4):
            upper = y <= edges[index + 1] if index == 3 else y < edges[index + 1]
            values.append(float(image[lung & (y >= edges[index]) & upper].sum()))
    return float(sum(values)), tuple(values)
