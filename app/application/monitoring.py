"""Qt-independent monitoring use case and presentation-ready read model."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
import logging
from threading import RLock
from collections.abc import Callable
import time
from typing import Protocol

import numpy as np

from ..config import DataMode
from ..data_sources import DataSource, DataSourceError, DataSourceState, RawMeasurementFrame
from ..domain import AcquisitionSettings, DataQuality, EITFrame, ReconstructionMap
from ..reconstruction.processor import RawFrameReconstructor, ReconstructionDiagnostics
from ..reconstruction.geometry import GeometryProfile, geometry_profile
from ..reconstruction.reconstruction import ReconstructionError
from .acquisition import AcquisitionMetrics, AcquisitionPipeline, SourceFrame
from .aeration import (
    AerationAlgorithmParameters, AerationProcessor, AerationResult,
    MetricAvailability,
)
from .peep import PeepProcessor, PeepResult
from .events import ApplicationEvent, EventBus, EventType
from ..technical_logging import get_logger, technical_event


FS = 25
DISPLAY_WINDOW_SEC = 60
DISPLAY_SAMPLES = FS * DISPLAY_WINDOW_SEC
BREATHS_IN_WINDOW = 12
_logger = get_logger("monitoring")


class MonitoringMode(str, Enum):
    LIVE = "live"
    PLAYBACK = "playback"


@dataclass(frozen=True, slots=True)
class MonitoringSnapshot:
    rr: float | None = None
    t_pct: float | None = None
    r_pct: float | None = None
    l_pct: float | None = None
    lr_ratio: float | None = None
    vd_ratio: float | None = None
    eeli: float | None = None
    eili: float | None = None
    tvi: float | None = None
    mvi: float | None = None
    phase: float | None = None
    roi_pct: tuple[float | None, ...] = field(default_factory=lambda: (None,) * 8)
    reconstruction_map: ReconstructionMap | None = None
    absolute_conductivity_map: ReconstructionMap | None = None
    trend_global: float | None = None
    trend_r: float | None = None
    trend_l: float | None = None
    roi_trends: tuple[float | None, ...] = field(default_factory=lambda: (None,) * 8)
    quality: DataQuality = DataQuality.UNAVAILABLE
    quality_reason: str | None = "insufficient_data"
    algorithm_version: str = "eit-aeration-mad-mean-3.2.0"
    metric_statuses: tuple[tuple[str, MetricAvailability], ...] = ()
    stream_state: str = "empty"
    analysis_window_seconds: float = 30.0
    selected_cycle_count: int | None = None
    complete_cycle_count: int = 0
    interval_start_seconds: float | None = None
    interval_end_seconds: float | None = None
    analyzed_sample_count: int = 0
    algorithm_parameters: AerationAlgorithmParameters = field(
        default_factory=AerationAlgorithmParameters
    )
    peep: PeepResult = field(default_factory=PeepResult)

    def status_for(self, metric: str) -> MetricAvailability:
        return dict(self.metric_statuses).get(
            metric, MetricAvailability(self.quality, self.quality_reason)
        )


@dataclass(frozen=True, slots=True)
class MonitoringView:
    """One atomic read for all widgets painted in the same UI tick."""

    snapshot: MonitoringSnapshot
    waveforms: dict[str, object]


@dataclass(frozen=True, slots=True)
class TrendSample:
    """One reconstructed, presentation-equivalent sample used by trend storage."""

    sequence_number: int
    timestamp_utc: datetime
    global_value: float | None
    roi_values: tuple[float | None, ...]
    quality: DataQuality
    quality_reason: str | None = None
    phase: float | None = None
    respiratory_rate_bpm: float | None = None
    metric_values: tuple[tuple[str, float | None], ...] = ()
    # Active-session position captured when the sample enters trend storage.
    # This is intentionally independent from an archived frame's source UTC.
    position_seconds: float | None = None


def _trend_metric_values(result: AerationResult) -> tuple[tuple[str, float | None], ...]:
    """Stable metric codes persisted with each sample and exposed by Trends."""
    values: list[tuple[str, float | None]] = [
        ("rr_bpm", result.respiratory_rate_bpm),
        ("tvi_au", result.tvi_au),
        ("mvi_au_per_min", result.minute_ventilation_au_per_min),
        ("eeli_au", result.eeli_au),
        ("eili_au", result.eili_au),
        ("right_percent", result.right_percent),
        ("left_percent", result.left_percent),
        ("right_left_ratio", result.right_left_ratio),
        ("ventral_dorsal_ratio", result.ventral_dorsal_ratio),
    ]
    values.extend(
        (f"roi_{index}_tvi_au", value)
        for index, value in enumerate(result.roi_tvi_au, start=1)
    )
    values.extend(
        (f"roi_{index}_percent", value)
        for index, value in enumerate(result.roi_percent, start=1)
    )
    return tuple(values)


class MonitoringData(Protocol):
    """Read model consumed by monitoring screens."""

    @property
    def snapshot(self) -> MonitoringSnapshot: ...
    @property
    def current_position_seconds(self) -> float: ...
    def advance(self) -> SourceFrame: ...
    def get_waveforms(self, window_sec: float = DISPLAY_WINDOW_SEC) -> dict[str, object]: ...
    def read_view(self, window_sec: float = DISPLAY_WINDOW_SEC) -> MonitoringView: ...
    def configure_aeration_analysis(
        self, *, window_seconds: float, cycle_count: int | None = None
    ) -> None: ...


class MonitoringService:
    """Owns acquisition lifecycle and hides the concrete source from the UI."""

    def __init__(
        self,
        source: DataSource,
        event_bus: EventBus,
        *,
        settings: AcquisitionSettings | None = None,
        buffer_seconds: int = 120,
        roi_count: int = 8,
        peak_detection_method: str = "mad_mean",
        peep_silent_threshold_percent: int = 10,
        peep_analysis_interval_seconds: int = 15,
        peep_gravity_angle_degrees: int = 0,
        geometry: GeometryProfile | None = None,
    ) -> None:
        self._source = source
        self._event_bus = event_bus
        self._settings = settings or AcquisitionSettings()
        self._buffer_seconds = buffer_seconds
        self._roi_count = roi_count
        self._peak_detection_method = peak_detection_method
        self._geometry_profile = geometry or geometry_profile("adult_ellipse")
        self._pending_geometry_profile: GeometryProfile | None = None
        capacity = max(1, int(buffer_seconds * self._settings.sample_rate_hz))
        self._aeration = AerationProcessor(
            AerationAlgorithmParameters(
                sample_rate_hz=self._settings.sample_rate_hz,
                roi_count=self._roi_count,
                peak_detection_method=self._peak_detection_method,
            ),
            capacity=capacity,
        )
        self._peep = PeepProcessor(
            sample_rate_hz=self._settings.sample_rate_hz,
            capacity=capacity,
            silent_threshold_percent=peep_silent_threshold_percent,
            analysis_interval_seconds=peep_analysis_interval_seconds,
            gravity_angle_degrees=peep_gravity_angle_degrees,
        )
        self._raw_reconstructor = RawFrameReconstructor(
            self._settings, geometry=self._geometry_profile
        )
        self._lock = RLock()
        self._started = False
        self._latest_frame: SourceFrame | None = None
        self._latest_reconstructed_frame: EITFrame | None = None
        self._pipeline: AcquisitionPipeline | None = None
        self._frame_handlers: list[Callable[[SourceFrame], None]] = []
        self._trend_sample_handlers: list[Callable[[TrendSample], None]] = []
        self._mode = MonitoringMode.LIVE
        self._last_frame_monotonic: float | None = None
        self._prime_reconstruction_reference()

    @property
    def source(self) -> DataSource:
        """Exposed for lifecycle diagnostics, never needed by screens."""
        return self._source

    @property
    def current_position_seconds(self) -> float:
        """Latest X coordinate on the aeration waveform time axis."""
        with self._lock:
            times = self._aeration.waveforms(1.0)["time"]
            return 0.0 if len(times) == 0 else max(0.0, float(times[-1]))

    @property
    def mode(self) -> MonitoringMode:
        return self._mode

    @property
    def read_only(self) -> bool:
        return self._mode is MonitoringMode.PLAYBACK

    @property
    def roi_count(self) -> int:
        return self._roi_count

    @property
    def is_running(self) -> bool:
        return (
            self._started
            and self._source.state is DataSourceState.RUNNING
            and self._pipeline is not None
            and self._pipeline.is_running
        )

    @property
    def acquisition_metrics(self) -> AcquisitionMetrics:
        if self._pipeline is None:
            return AcquisitionMetrics()
        return self._pipeline.snapshot().metrics

    @property
    def acquisition_frames(self) -> tuple[SourceFrame, ...]:
        if self._pipeline is None:
            return ()
        return self._pipeline.snapshot().frames

    @property
    def reconstruction_diagnostics(self) -> ReconstructionDiagnostics:
        return self._raw_reconstructor.diagnostics

    @property
    def section_profile(self) -> GeometryProfile:
        """Geometry currently used by reconstruction (not a deferred selection)."""

        return self._geometry_profile

    def subscribe_frames(
        self, handler: Callable[[SourceFrame], None]
    ) -> Callable[[], None]:
        with self._lock:
            self._frame_handlers.append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._frame_handlers:
                    self._frame_handlers.remove(handler)

        return unsubscribe

    def subscribe_trend_samples(
        self, handler: Callable[[TrendSample], None]
    ) -> Callable[[], None]:
        """Subscribe to reconstructed/filtered samples without changing raw recording."""
        with self._lock:
            self._trend_sample_handlers.append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._trend_sample_handlers:
                    self._trend_sample_handlers.remove(handler)

        return unsubscribe

    def start(self) -> None:
        if self._started:
            return
        self._reset_buffers()
        try:
            devices = self._source.discover()
            device_id = devices[0].id if devices else None
            self._source.connect(device_id)
            self._publish_state()
            self._source.configure(self._settings)
            self._publish_state()
            self._source.start()
            self._started = True
            self._start_pipeline()
            self._publish_state()
        except Exception:
            # A failed connect/configure/start must never leave a half-open
            # device behind: the session controller can then roll back safely.
            self._stop_pipeline()
            try:
                if self._source.state is DataSourceState.RUNNING:
                    self._source.stop()
                if self._source.state is not DataSourceState.DISCONNECTED:
                    self._source.disconnect()
            finally:
                self._started = False
                self._publish_state()
            raise

    def suspend(self) -> None:
        """Pause acquisition without disconnecting or resetting source sequence."""
        if not self._started:
            return
        self._stop_pipeline()
        if self._source.state is DataSourceState.RUNNING:
            self._source.stop()
        self._publish_state()

    def resume(self) -> None:
        """Resume a suspended source while preserving the current data buffers."""
        if not self._started:
            raise DataSourceError("monitoring service has not been started")
        if self._source.state is DataSourceState.CONFIGURED:
            self._source.start()
        if self._source.state is not DataSourceState.RUNNING:
            raise DataSourceError("monitoring source cannot be resumed")
        self._start_pipeline()
        self._publish_state()

    def configure(self, settings: AcquisitionSettings) -> None:
        """Apply validated settings to the source, preserving its run state."""
        if not isinstance(settings, AcquisitionSettings):
            raise TypeError("settings must be AcquisitionSettings")
        was_running = self._source.state is DataSourceState.RUNNING
        if was_running:
            self._stop_pipeline()
            self._source.stop()
            self._publish_state()
        if self._source.state is DataSourceState.DISCONNECTED:
            devices = self._source.discover()
            self._source.connect(devices[0].id if devices else None)
            self._publish_state()
        self._source.configure(settings)
        self._settings = settings
        capacity = max(1, int(self._buffer_seconds * settings.sample_rate_hz))
        with self._lock:
            self._aeration = AerationProcessor(
                AerationAlgorithmParameters(
                    sample_rate_hz=settings.sample_rate_hz,
                    roi_count=self._roi_count,
                    peak_detection_method=self._peak_detection_method,
                ),
                capacity=capacity,
            )
            self._raw_reconstructor = RawFrameReconstructor(
                settings, geometry=self._geometry_profile
            )
            self._prime_reconstruction_reference()
        self._publish_state()
        if was_running:
            self._source.start()
            self._start_pipeline()
            self._publish_state()

    def set_roi_count(self, roi_count: int) -> None:
        """Apply a new regional resolution to subsequent maps and metrics."""
        self.set_aeration_configuration(
            roi_count=roi_count,
            peak_detection_method=self._peak_detection_method,
        )

    def set_section_profile(self, profile: GeometryProfile) -> bool:
        """Select reconstruction geometry; defer a running-session change safely."""

        if not isinstance(profile, GeometryProfile):
            raise TypeError("profile must be a GeometryProfile")
        with self._lock:
            if profile.cache_key() == self._geometry_profile.cache_key():
                return True
            if self.is_running:
                self._pending_geometry_profile = profile
                return False
            self._geometry_profile = profile
            self._pending_geometry_profile = None
            self._raw_reconstructor = RawFrameReconstructor(
                self._settings, geometry=profile
            )
            self._prime_reconstruction_reference()
            self._latest_reconstructed_frame = None
        return True

    def set_aeration_configuration(
        self, *, roi_count: int, peak_detection_method: str
    ) -> None:
        """Apply engineering aeration settings and reset the analysis buffer."""
        parameters = AerationAlgorithmParameters(
            sample_rate_hz=self._settings.sample_rate_hz,
            roi_count=roi_count,
            peak_detection_method=peak_detection_method,
        )
        with self._lock:
            if (
                roi_count == self._roi_count
                and peak_detection_method == self._peak_detection_method
            ):
                return
            self._roi_count = roi_count
            self._peak_detection_method = peak_detection_method
            self._aeration = AerationProcessor(
                parameters,
                capacity=max(1, int(self._buffer_seconds * self._settings.sample_rate_hz)),
            )

    def stop(self) -> None:
        if not self._started:
            self._reset_buffers()
            return
        self._stop_pipeline()
        if self._source.state is DataSourceState.RUNNING:
            self._source.stop()
            self._publish_state()
        self._source.disconnect()
        self._started = False
        self._reset_buffers()
        self._publish_state()

    def replace_source(
        self,
        source: DataSource,
        settings: AcquisitionSettings,
        *,
        mode: MonitoringMode = MonitoringMode.LIVE,
        start: bool = True,
    ) -> None:
        """Atomically replace the acquisition source and reset presentation data."""
        self.stop()
        self._source = source
        self._settings = settings
        self._mode = mode
        capacity = max(1, int(self._buffer_seconds * settings.sample_rate_hz))
        with self._lock:
            self._aeration = AerationProcessor(
                AerationAlgorithmParameters(
                    sample_rate_hz=settings.sample_rate_hz,
                    roi_count=self._roi_count,
                    peak_detection_method=self._peak_detection_method,
                ),
                capacity=capacity,
            )
            self._raw_reconstructor = RawFrameReconstructor(
                settings, geometry=self._geometry_profile
            )
            self._prime_reconstruction_reference()
            self._latest_frame = None
            self._latest_reconstructed_frame = None
            self._last_frame_monotonic = None
        if start:
            self.start()

    def seek_playback(self, seconds: float) -> float:
        """Seek the active read-only source and resume it with an empty UI buffer."""
        if self._mode is not MonitoringMode.PLAYBACK or not hasattr(self._source, "seek"):
            raise DataSourceError("no recording is active")
        self._stop_pipeline()
        if self._source.state is DataSourceState.RUNNING:
            self._source.stop()
        position = float(self._source.seek(seconds))
        self._reset_buffers()
        self._source.start()
        self._start_pipeline()
        self._publish_state()
        return position

    def set_playback_speed(self, speed: float) -> None:
        if self._mode is not MonitoringMode.PLAYBACK or not hasattr(
            type(self._source), "playback_speed"
        ):
            raise DataSourceError("no recording is active")
        self._stop_pipeline()
        self._source.playback_speed = speed
        if self._source.state is DataSourceState.RUNNING:
            self._start_pipeline()
        self._publish_state()

    def pause_playback(self) -> None:
        if self._mode is not MonitoringMode.PLAYBACK:
            raise DataSourceError("no recording is active")
        self._stop_pipeline()
        if self._source.state is DataSourceState.RUNNING:
            self._source.stop()
        self._publish_state()

    def resume_playback(self) -> None:
        if self._mode is not MonitoringMode.PLAYBACK:
            raise DataSourceError("no recording is active")
        if self._source.state is DataSourceState.CONFIGURED:
            self._source.start()
        if self._source.state is DataSourceState.RUNNING:
            self._start_pipeline()
        self._publish_state()

    def advance(self) -> SourceFrame:
        if not self._started:
            self.start()
        pipeline = self._pipeline
        if pipeline is None:
            raise DataSourceError("acquisition pipeline is not running")
        snapshot = pipeline.snapshot()
        if not snapshot.frames:
            snapshot = pipeline.wait_for_received(1, self._source.timing_policy.read_timeout_seconds)
        if not snapshot.frames:
            error = pipeline.last_error
            if error is not None:
                raise error
            raise DataSourceError("no acquisition frame is available")
        return snapshot.frames[-1]

    def prime(self, sample_count: int) -> None:
        """Fill the read model before first paint (used by the demo source)."""
        if sample_count < 0:
            raise ValueError("sample_count must be non-negative")
        if sample_count == 0:
            return
        pipeline = self._pipeline
        if pipeline is None:
            raise DataSourceError("acquisition pipeline is not running")
        initial = pipeline.snapshot().metrics.received_frames
        pipeline.wait_for_received(
            initial + sample_count,
            max(1.0, sample_count / self._settings.sample_rate_hz * 2.0),
        )

    def get_waveforms(self, window_sec: float = DISPLAY_WINDOW_SEC) -> dict[str, object]:
        with self._lock:
            return self._aeration.waveforms(window_sec)

    @property
    def latest_delta_map(self) -> ReconstructionMap | None:
        """Read just the immutable map needed to latch a hidden widget's scale."""
        with self._lock:
            frame = self._latest_reconstructed_frame
            return frame.reconstructed_delta_z if frame is not None else None

    def configure_aeration_analysis(
        self, *, window_seconds: float, cycle_count: int | None = None
    ) -> None:
        """Configure the deterministic interval/cycle selection used by metrics."""
        with self._lock:
            self._aeration.configure_analysis(
                window_seconds=window_seconds, cycle_count=cycle_count
            )

    def configure_peep_analysis(
        self,
        *,
        silent_threshold_percent: int,
        analysis_interval_seconds: int,
        gravity_angle_degrees: int,
    ) -> None:
        with self._lock:
            self._peep.configure(
                silent_threshold_percent=silent_threshold_percent,
                analysis_interval_seconds=analysis_interval_seconds,
                gravity_angle_degrees=gravity_angle_degrees,
            )

    def read_view(self, window_sec: float = DISPLAY_WINDOW_SEC) -> MonitoringView:
        """Capture one data version, then calculate trends outside the acquisition lock."""
        return self._read_view(window_sec)

    @property
    def snapshot(self) -> MonitoringSnapshot:
        return self._read_view(DISPLAY_WINDOW_SEC).snapshot

    def _read_view(self, window_sec: float) -> MonitoringView:
        with self._lock:
            waves = self._aeration.waveforms(max(window_sec, DISPLAY_WINDOW_SEC))
            sample_rate = self._aeration.parameters.sample_rate_hz
            selection_window, _ = self._aeration.analysis_selection
            result = self._aeration.result()
            peep_result = self._peep.result()
            stream_state = self._stream_state_locked()
            reconstruction_map = (
                self._latest_reconstructed_frame.reconstructed_delta_z
                if self._latest_reconstructed_frame is not None
                else None
            )
            absolute_conductivity_map = (
                self._latest_reconstructed_frame.absolute_conductivity
                if self._latest_reconstructed_frame is not None
                else None
            )
            reconstruction_diagnostics = self._raw_reconstructor.diagnostics
            if (
                isinstance(self._latest_frame, RawMeasurementFrame)
                and reconstruction_diagnostics.ready
                and not reconstruction_diagnostics.assumptions_confirmed
                and result.quality is DataQuality.DEGRADED
                and result.quality_reason == "source_quality_degraded"
            ):
                reason = "reconstruction_assumptions_unconfirmed"
                result = replace(
                    result,
                    quality_reason=reason,
                    metric_statuses=tuple(
                        (
                            name,
                            MetricAvailability(status.quality, reason)
                            if status.reason == "source_quality_degraded"
                            else status,
                        )
                        for name, status in result.metric_statuses
                    ),
                )
            if result.available and stream_state in {"frozen", "lost"}:
                reason = (
                    "data_stream_lost" if stream_state == "lost"
                    else "monitoring_paused"
                )
                statuses = tuple(
                    (
                        name,
                        status if status.quality is DataQuality.UNAVAILABLE
                        else MetricAvailability(DataQuality.STALE, reason),
                    )
                    for name, status in result.metric_statuses
                )
                result = replace(
                    result,
                    quality=DataQuality.STALE,
                    quality_reason=reason,
                    metric_statuses=statuses,
                )
        trend_count = max(1, int(DISPLAY_WINDOW_SEC * sample_rate))
        global_values = waves["global"][-trend_count:]
        roi_values = [values[-trend_count:] for values in waves["rois"]]
        snapshot = self._build_snapshot(result, peep_result, stream_state, selection_window,
                                        reconstruction_map, absolute_conductivity_map,
                                        global_values, roi_values)
        if window_sec < DISPLAY_WINDOW_SEC:
            count = max(1, int(window_sec * sample_rate))
            waves = {
                "time": waves["time"][-count:],
                "global": waves["global"][-count:],
                "velocity": waves["velocity"][-count:],
                "rois": [values[-count:] for values in roi_values],
            }
        return MonitoringView(snapshot, waves)

    @staticmethod
    def _build_snapshot(result, peep_result, stream_state, selection_window,
                        reconstruction_map, absolute_conductivity_map,
                        global_values, roi_values) -> MonitoringSnapshot:
        roi_count = len(roi_values)
        if global_values.size == 0:
            return MonitoringSnapshot(
                quality=result.quality,
                quality_reason=result.quality_reason,
                algorithm_version=result.algorithm_version,
                metric_statuses=result.metric_statuses,
                stream_state=stream_state,
                reconstruction_map=reconstruction_map,
                absolute_conductivity_map=absolute_conductivity_map,
                analysis_window_seconds=selection_window,
                selected_cycle_count=result.selected_cycle_count,
                complete_cycle_count=result.complete_cycle_count,
                interval_start_seconds=result.interval_start_seconds,
                interval_end_seconds=result.interval_end_seconds,
                analyzed_sample_count=result.analyzed_sample_count,
                algorithm_parameters=result.parameters,
                peep=peep_result,
                roi_pct=result.roi_percent,
                roi_trends=(None,) * roi_count,
            )

        roi_pct = result.roi_percent

        trends_available = result.quality in {DataQuality.VALID, DataQuality.DEGRADED}
        return MonitoringSnapshot(
            rr=result.respiratory_rate_bpm,
            t_pct=100.0 if result.available else None,
            r_pct=result.right_percent,
            l_pct=result.left_percent,
            lr_ratio=result.right_left_ratio,
            vd_ratio=result.ventral_dorsal_ratio,
            eeli=result.eeli_au,
            eili=result.eili_au,
            tvi=result.tvi_au,
            mvi=result.minute_ventilation_au_per_min,
            phase=result.phase,
            roi_pct=roi_pct,
            reconstruction_map=reconstruction_map,
            absolute_conductivity_map=absolute_conductivity_map,
            trend_global=_trend(global_values) if trends_available else None,
            trend_r=(
                _trend(_mean_channels(roi_values[:roi_count // 2]))
                if trends_available else None
            ),
            trend_l=(
                _trend(_mean_channels(roi_values[roi_count // 2:]))
                if trends_available else None
            ),
            roi_trends=tuple(
                _trend(values) if trends_available else None for values in roi_values
            ),
            quality=result.quality,
            quality_reason=result.quality_reason,
            algorithm_version=result.algorithm_version,
            metric_statuses=result.metric_statuses,
            stream_state=stream_state,
            analysis_window_seconds=selection_window,
            selected_cycle_count=result.selected_cycle_count,
            complete_cycle_count=result.complete_cycle_count,
            interval_start_seconds=result.interval_start_seconds,
            interval_end_seconds=result.interval_end_seconds,
            analyzed_sample_count=result.analyzed_sample_count,
            algorithm_parameters=result.parameters,
            peep=peep_result,
        )

    def _publish_state(self) -> None:
        technical_event(
            _logger,
            logging.INFO,
            "data_source.state_changed",
            state=self._source.state.value,
            mode=self._source.mode.value,
            source_type=type(self._source).__name__,
        )
        self._event_bus.publish(
            ApplicationEvent(
                EventType.DATA_SOURCE_STATE_CHANGED,
                payload={
                    "state": self._source.state.value,
                    "mode": self._source.mode.value,
                },
            )
        )

    def _start_pipeline(self) -> None:
        capacity = max(1, int(self._buffer_seconds * self._settings.sample_rate_hz))
        interval = None
        if (
            self._source.mode in {DataMode.SIMULATION, DataMode.FROMFILE}
            or self._mode is MonitoringMode.PLAYBACK
        ):
            speed = float(getattr(self._source, "playback_speed", 1.0))
            interval = 1.0 / (self._settings.sample_rate_hz * speed)
        self._pipeline = AcquisitionPipeline(
            self._source,
            capacity=capacity,
            frame_interval_seconds=interval,
            on_frame=self._accept_frame,
        )
        self._pipeline.start()

    def _reset_buffers(self) -> None:
        capacity = max(1, int(self._buffer_seconds * self._settings.sample_rate_hz))
        with self._lock:
            if self._pending_geometry_profile is not None and not self.is_running:
                self._geometry_profile = self._pending_geometry_profile
                self._pending_geometry_profile = None
                self._raw_reconstructor = RawFrameReconstructor(
                    self._settings, geometry=self._geometry_profile
                )
            self._aeration.reset()
            self._peep.reset()
            self._raw_reconstructor.reset()
            self._prime_reconstruction_reference()
            self._latest_frame = None
            self._latest_reconstructed_frame = None
            self._last_frame_monotonic = None

    def _prime_reconstruction_reference(self) -> None:
        frames = getattr(self._source, "reconstruction_reference_frames", None)
        if frames:
            self._raw_reconstructor.prime_reference(frames)

    def _stop_pipeline(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()

    def _accept_frame(self, frame: SourceFrame) -> None:
        trend_sample = None
        with self._lock:
            self._latest_frame = frame
            self._last_frame_monotonic = time.monotonic()
            if isinstance(frame, EITFrame):
                reconstructed = frame
            else:
                try:
                    reconstructed = self._raw_reconstructor.process(frame)
                except (ValueError, ReconstructionError, np.linalg.LinAlgError) as exc:
                    technical_event(
                        _logger,
                        logging.ERROR,
                        "reconstruction.failed",
                        sequence_number=frame.sequence_number,
                        error_type=type(exc).__name__,
                    )
                    raise DataSourceError(
                        f"EIT reconstruction failed: {exc}"
                    ) from exc
            if reconstructed is not None:
                self._latest_reconstructed_frame = reconstructed
                self._peep.process(
                    reconstructed.reconstructed_delta_z,
                    reconstructed.global_impedance,
                )
                processed = self._aeration.process(reconstructed)
                analysis = self._aeration.result()
                if processed is None:
                    trend_sample = TrendSample(
                        sequence_number=reconstructed.sequence_number,
                        timestamp_utc=reconstructed.timestamp_utc,
                        global_value=None,
                        roi_values=(None,) * self._roi_count,
                        quality=self._aeration.quality,
                        quality_reason=self._aeration.quality_reason,
                        phase=analysis.phase,
                        respiratory_rate_bpm=analysis.respiratory_rate_bpm,
                        metric_values=_trend_metric_values(analysis),
                    )
                else:
                    trend_sample = TrendSample(
                        sequence_number=processed.sequence_number,
                        timestamp_utc=reconstructed.timestamp_utc,
                        global_value=processed.global_impedance,
                        roi_values=tuple(processed.roi_impedance),
                        quality=analysis.quality,
                        quality_reason=analysis.quality_reason,
                        phase=analysis.phase,
                        respiratory_rate_bpm=analysis.respiratory_rate_bpm,
                        metric_values=_trend_metric_values(analysis),
                    )
            handlers = tuple(self._frame_handlers)
            trend_handlers = tuple(self._trend_sample_handlers)
        for handler in handlers:
            handler(frame)
        if trend_sample is not None:
            for handler in trend_handlers:
                handler(trend_sample)
        self._event_bus.publish(
            ApplicationEvent(
                EventType.FRAME_RECEIVED,
                occurred_at_utc=frame.timestamp_utc,
                payload={
                    "sequence_number": frame.sequence_number,
                    "quality": frame.quality.value,
                    "simulated": frame.simulated,
                    "raw": isinstance(frame, RawMeasurementFrame),
                },
            )
        )

    def _stream_state_locked(self) -> str:
        if self._latest_frame is None:
            return "empty"
        pipeline_error = self._pipeline.last_error if self._pipeline is not None else None
        if pipeline_error is not None:
            return "lost"
        if self.is_running:
            timeout = max(2.0, self._source.timing_policy.read_timeout_seconds * 2.0)
            if (
                self._last_frame_monotonic is not None
                and time.monotonic() - self._last_frame_monotonic > timeout
            ):
                return "lost"
            return "live"
        return "frozen" if self._started else "empty"


def _trend(values: np.ndarray, window: int = DISPLAY_SAMPLES) -> float:
    """Robust level change across the visible window, resistant to breath phase."""
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size < 2:
        return 0.0
    selected = finite[-window:]
    x = np.linspace(0.0, 1.0, selected.size)
    start = float(np.median(selected[:max(1, selected.size // 4)]))
    centered_x = x - float(np.mean(x))
    level_change = float(
        np.dot(centered_x, selected - float(np.mean(selected)))
        / np.dot(centered_x, centered_x)
    )
    amplitude = float(np.ptp(selected))
    base = max(abs(start), amplitude, 0.05)
    return float(np.clip(level_change / base * 100.0, -99.0, 99.0))


def _mean_channels(channels: list[np.ndarray]) -> np.ndarray:
    populated = [values for values in channels if values.size]
    if not populated:
        return np.asarray([], dtype=float)
    return np.mean(populated, axis=0)
