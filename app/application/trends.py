"""Incremental persistence and range reads for long-running trend data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from threading import RLock
from uuid import UUID

from .acquisition import SourceFrame
from .events import ApplicationEvent, EventBus, EventType
from .monitoring import MonitoringService
from .ports import TrendRepository
from .studies import StudyLifecycleService
from ..domain import DataQuality, EITFrame, StudyStatus, TrendAggregate


TREND_INTERVAL_SECONDS = 15.0
TREND_ALGORITHM_VERSION = "eit-trend-median-1.0.0"


@dataclass(frozen=True, slots=True)
class TrendSeries:
    study_id: UUID
    points: tuple[TrendAggregate, ...]


class TrendService:
    """Writes bounded aggregates while frames arrive; never rescans raw history."""

    def __init__(
        self,
        repository: TrendRepository,
        monitoring: MonitoringService,
        lifecycle: StudyLifecycleService,
        event_bus: EventBus,
        *,
        interval_seconds: float = TREND_INTERVAL_SECONDS,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._repository = repository
        self._monitoring = monitoring
        self._lifecycle = lifecycle
        self._interval_seconds = float(interval_seconds)
        self._lock = RLock()
        self._interval_frames: list[EITFrame] = []
        self._cycle_frames: list[EITFrame] = []
        self._last_phase: float | None = None
        self._unsubscribe_frames = monitoring.subscribe_frames(self._on_frame)
        self._unsubscribe_study = event_bus.subscribe(
            EventType.STUDY_CHANGED, self._on_study_changed
        )
        self._unsubscribe_markers = event_bus.subscribe(
            EventType.MARKERS_CHANGED, self._on_marker_changed
        )

    def close(self) -> None:
        self.flush()
        self._unsubscribe_frames()
        self._unsubscribe_study()
        self._unsubscribe_markers()

    def flush(self) -> None:
        with self._lock:
            self._flush_frames(self._interval_frames, "interval")
            self._flush_frames(self._cycle_frames, "breath_cycle")
            self._interval_frames.clear()
            self._cycle_frames.clear()
            self._last_phase = None

    def read(
        self,
        study_id: UUID,
        start_utc: datetime,
        end_utc: datetime,
        *,
        aggregation_kind: str = "interval",
    ) -> TrendSeries:
        return TrendSeries(
            study_id,
            tuple(self._repository.list_range(
                study_id, start_utc, end_utc, aggregation_kind=aggregation_kind
            )),
        )

    def bounds(self, study_id: UUID):
        return self._repository.bounds(study_id)

    def _on_frame(self, frame: SourceFrame) -> None:
        if not isinstance(frame, EITFrame) or self._lifecycle.status is not StudyStatus.RUNNING:
            return
        with self._lock:
            if self._interval_frames and (
                frame.timestamp_utc - self._interval_frames[0].timestamp_utc
            ).total_seconds() >= self._interval_seconds:
                self._flush_frames(self._interval_frames, "interval")
                self._interval_frames.clear()
            self._interval_frames.append(frame)
            self._cycle_frames.append(frame)

            phase = self._monitoring.snapshot.phase
            completed_cycle = (
                phase is not None
                and self._last_phase is not None
                and self._last_phase >= 0.75
                and phase <= 0.25
            )
            self._last_phase = phase
            if completed_cycle and len(self._cycle_frames) > 1:
                self._flush_frames(self._cycle_frames, "breath_cycle")
                self._cycle_frames.clear()

    def _on_study_changed(self, _event: ApplicationEvent) -> None:
        if self._lifecycle.status in {StudyStatus.COMPLETED, StudyStatus.FAILED}:
            self.flush()

    def _on_marker_changed(self, _event: ApplicationEvent) -> None:
        # Persist the partial interval so a newly created marker can immediately
        # be placed on the same durable timeline.
        with self._lock:
            self._flush_frames(self._interval_frames, "interval")
            self._interval_frames.clear()

    def _flush_frames(self, frames: list[EITFrame], kind: str) -> None:
        study = self._lifecycle.current_study
        session = self._lifecycle.current_session
        if not frames or study is None or session is None or session.started_at_utc is None:
            return
        snap = self._monitoring.snapshot
        roi_values = tuple(
            median(frame.roi_impedance[index] for frame in frames) for index in range(8)
        )
        qualities = {frame.quality for frame in frames}
        quality = (
            DataQuality.UNAVAILABLE if DataQuality.UNAVAILABLE in qualities else
            DataQuality.STALE if DataQuality.STALE in qualities else
            DataQuality.DEGRADED if DataQuality.DEGRADED in qualities else
            DataQuality.VALID
        )
        end = frames[-1].timestamp_utc
        aggregate = TrendAggregate(
            study_id=study.id,
            session_id=session.id,
            interval_start_utc=frames[0].timestamp_utc,
            interval_end_utc=end,
            position_seconds=max(0.0, (end - session.started_at_utc).total_seconds()),
            aggregation_kind=kind,
            sample_count=len(frames),
            global_value=median(frame.global_impedance for frame in frames),
            right_value=median(sum(frame.roi_impedance[:4]) for frame in frames),
            left_value=median(sum(frame.roi_impedance[4:]) for frame in frames),
            roi_values=roi_values,
            respiratory_rate_bpm=snap.rr,
            quality=quality,
            quality_reason=snap.quality_reason,
            algorithm_version=TREND_ALGORITHM_VERSION,
            simulated=study.simulated,
        )
        self._repository.append(aggregate)
