"""Qt-independent monitoring use case and presentation-ready read model."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
from ..reconstruction.reconstruction import ReconstructionError
from .acquisition import AcquisitionMetrics, AcquisitionPipeline, SourceFrame
from .aeration import (
    AerationAlgorithmParameters, AerationProcessor, MetricAvailability,
)
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
    phase: float | None = None
    roi_pct: tuple[float | None, ...] = field(default_factory=lambda: (None,) * 8)
    reconstruction_map: ReconstructionMap | None = None
    absolute_conductivity_map: ReconstructionMap | None = None
    trend_global: float = 0.0
    trend_r: float = 0.0
    trend_l: float = 0.0
    roi_trends: tuple[float, ...] = field(default_factory=lambda: (0.0,) * 8)
    quality: DataQuality = DataQuality.UNAVAILABLE
    quality_reason: str | None = "insufficient_data"
    algorithm_version: str = "eit-aeration-derivative-2.0.0"
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

    def status_for(self, metric: str) -> MetricAvailability:
        return dict(self.metric_statuses).get(
            metric, MetricAvailability(self.quality, self.quality_reason)
        )


@dataclass(frozen=True, slots=True)
class MonitoringView:
    """One atomic read for all widgets painted in the same UI tick."""

    snapshot: MonitoringSnapshot
    waveforms: dict[str, object]


class MonitoringData(Protocol):
    """Read model consumed by monitoring screens."""

    @property
    def snapshot(self) -> MonitoringSnapshot: ...
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
        buffer_seconds: int = 90,
        roi_count: int = 8,
        peak_detection_method: str = "derivative",
    ) -> None:
        self._source = source
        self._event_bus = event_bus
        self._settings = settings or AcquisitionSettings()
        self._buffer_seconds = buffer_seconds
        self._roi_count = roi_count
        self._peak_detection_method = peak_detection_method
        capacity = max(1, int(buffer_seconds * self._settings.sample_rate_hz))
        self._aeration = AerationProcessor(
            AerationAlgorithmParameters(
                sample_rate_hz=self._settings.sample_rate_hz,
                roi_count=self._roi_count,
                peak_detection_method=self._peak_detection_method,
            ),
            capacity=capacity,
        )
        self._raw_reconstructor = RawFrameReconstructor(self._settings)
        self._lock = RLock()
        self._started = False
        self._latest_frame: SourceFrame | None = None
        self._latest_reconstructed_frame: EITFrame | None = None
        self._pipeline: AcquisitionPipeline | None = None
        self._frame_handlers: list[Callable[[SourceFrame], None]] = []
        self._mode = MonitoringMode.LIVE
        self._last_frame_monotonic: float | None = None
        self._prime_reconstruction_reference()

    @property
    def source(self) -> DataSource:
        """Exposed for lifecycle diagnostics, never needed by screens."""
        return self._source

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
            self._raw_reconstructor = RawFrameReconstructor(settings)
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
            self._raw_reconstructor = RawFrameReconstructor(settings)
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
            waves = self._aeration.waveforms(window_sec)
            # Keep the public result independent from processor-owned arrays.
            return {
                "time": waves["time"].copy(),
                "global": waves["global"].copy(),
                "rois": [values.copy() for values in waves["rois"]],
            }

    def configure_aeration_analysis(
        self, *, window_seconds: float, cycle_count: int | None = None
    ) -> None:
        """Configure the deterministic interval/cycle selection used by metrics."""
        with self._lock:
            self._aeration.configure_analysis(
                window_seconds=window_seconds, cycle_count=cycle_count
            )

    def read_view(self, window_sec: float = DISPLAY_WINDOW_SEC) -> MonitoringView:
        """Return synchronized curves and metrics while acquisition is locked."""
        with self._lock:
            return MonitoringView(
                snapshot=self.snapshot,
                waveforms=self.get_waveforms(window_sec),
            )

    @property
    def snapshot(self) -> MonitoringSnapshot:
        with self._lock:
            result = self._aeration.result()
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
        waves = self.get_waveforms()
        global_values = waves["global"]
        roi_values = waves["rois"]
        if not isinstance(global_values, np.ndarray) or global_values.size == 0:
            selection_window, _ = self._aeration.analysis_selection
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
                roi_pct=result.roi_percent,
                roi_trends=(0.0,) * self._roi_count,
            )

        roi_pct = result.roi_percent

        selection_window, _ = self._aeration.analysis_selection
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
            phase=result.phase,
            roi_pct=roi_pct,
            reconstruction_map=reconstruction_map,
            absolute_conductivity_map=absolute_conductivity_map,
            trend_global=_trend(global_values),
            trend_r=_trend(_mean_channels(roi_values[:self._roi_count // 2])),
            trend_l=_trend(_mean_channels(roi_values[self._roi_count // 2:])),
            roi_trends=tuple(_trend(values) for values in roi_values),
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
            self._aeration.reset()
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
                self._aeration.process(reconstructed)
            handlers = tuple(self._frame_handlers)
        for handler in handlers:
            handler(frame)
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


def _trend(values: np.ndarray, window: int = 50) -> float:
    if values.size < 2:
        return 0.0
    selected = values[-window:]
    base = max(abs(float(selected[0])), 0.05)
    return float(np.clip((float(selected[-1]) - float(selected[0])) / base * 100.0, -99.0, 99.0))


def _mean_channels(channels: list[np.ndarray]) -> np.ndarray:
    populated = [values for values in channels if values.size]
    if not populated:
        return np.asarray([], dtype=float)
    return np.mean(populated, axis=0)
