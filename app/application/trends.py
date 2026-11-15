"""Incremental persistence and range reads for long-running trend data."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from collections.abc import Callable
from statistics import median
from threading import RLock
from uuid import UUID

from .events import ApplicationEvent, EventBus, EventType
from .monitoring import MonitoringService, TrendSample
from .ports import TrendRepository
from .studies import StudyLifecycleService
from ..domain import DataQuality, StudyStatus, TrendAggregate, utc_now


TREND_INTERVAL_SECONDS = 15.0
TREND_ALGORITHM_VERSION = "eit-trend-median-3.0.0"


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
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._repository = repository
        self._monitoring = monitoring
        self._lifecycle = lifecycle
        self._interval_seconds = float(interval_seconds)
        self._clock = clock
        self._position_session_id: UUID | None = None
        self._source_time_origin: datetime | None = None
        self._source_position_origin = 0.0
        self._lock = RLock()
        self._interval_frames: list[TrendSample] = []
        self._cycle_frames: list[TrendSample] = []
        self._last_phase: float | None = None
        self._cycle_started = False
        self._unsubscribe_frames = monitoring.subscribe_trend_samples(self._on_frame)
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
            self._interval_frames.clear()
            # Only detected complete cycles are persisted as breath_cycle points.
            self._cycle_frames.clear()
            self._last_phase = None
            self._cycle_started = False

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

    def position_bounds(
        self, study_id: UUID, *, aggregation_kind: str = "interval"
    ):
        return self._repository.position_bounds(
            study_id, aggregation_kind=aggregation_kind
        )

    def baseline(self, study_id: UUID, *, aggregation_kind: str = "interval"):
        return self._repository.first_usable(
            study_id, aggregation_kind=aggregation_kind
        )

    def read_position(
        self,
        study_id: UUID,
        start_seconds: float,
        end_seconds: float,
        *,
        aggregation_kind: str = "interval",
    ) -> TrendSeries:
        return TrendSeries(
            study_id,
            tuple(self._repository.list_position_range(
                study_id,
                start_seconds,
                end_seconds,
                aggregation_kind=aggregation_kind,
            )),
        )

    def _on_frame(self, frame: TrendSample) -> None:
        if self._lifecycle.status is not StudyStatus.RUNNING:
            return
        session = self._lifecycle.current_session
        if (
            frame.position_seconds is None
            and session is not None
            and session.started_at_utc is not None
        ):
            # Device/simulation timestamps belong to the active session.  A
            # fromfile frame may retain an archived UTC timestamp, in which
            # case its position must follow the current playback session.
            if self._position_session_id != session.id:
                self._position_session_id = session.id
                self._source_time_origin = None
            if frame.timestamp_utc >= session.started_at_utc:
                position = session.duration_seconds(frame.timestamp_utc)
            else:
                # Legacy/archive timestamps are mapped once onto a logical
                # source-time axis.  Never use variable CPU processing speed as
                # the X coordinate of a continuous file generator.
                if self._source_time_origin is None:
                    self._source_time_origin = frame.timestamp_utc
                    self._source_position_origin = session.duration_seconds(
                        self._clock()
                    )
                position = self._source_position_origin + max(
                    0.0,
                    (frame.timestamp_utc - self._source_time_origin).total_seconds(),
                )
            frame = replace(
                frame,
                position_seconds=position,
            )
        with self._lock:
            if self._interval_frames and (
                frame.timestamp_utc - self._interval_frames[0].timestamp_utc
            ).total_seconds() >= self._interval_seconds:
                self._flush_frames(self._interval_frames, "interval")
                self._interval_frames.clear()
            self._interval_frames.append(frame)

            phase = frame.phase
            completed_cycle = (
                phase is not None
                and self._last_phase is not None
                and self._last_phase >= 0.75
                and phase <= 0.25
            )
            self._last_phase = phase
            if self._cycle_started:
                self._cycle_frames.append(frame)
            if completed_cycle:
                if self._cycle_started and len(self._cycle_frames) > 1:
                    self._flush_frames(self._cycle_frames, "breath_cycle")
                self._cycle_started = True
                self._cycle_frames = [frame]

    def _on_study_changed(self, _event: ApplicationEvent) -> None:
        if self._lifecycle.status in {
            StudyStatus.PAUSED, StudyStatus.COMPLETED, StudyStatus.FAILED
        }:
            self.flush()

    def _on_marker_changed(self, _event: ApplicationEvent) -> None:
        # Persist the partial interval so a newly created marker can immediately
        # be placed on the same durable timeline.
        with self._lock:
            self._flush_frames(self._interval_frames, "interval")
            self._interval_frames.clear()

    def _flush_frames(self, frames: list[TrendSample], kind: str) -> None:
        study = self._lifecycle.current_study
        session = self._lifecycle.current_session
        if not frames or study is None or session is None or session.started_at_utc is None:
            return
        roi_count = max((len(frame.roi_values) for frame in frames), default=0)
        regional = [
            [
                frame.roi_values[index]
                for frame in frames
                if index < len(frame.roi_values) and frame.roi_values[index] is not None
            ]
            for index in range(roi_count)
        ]
        roi_values = tuple(
            median(float(value) for value in values) if values else None
            for values in regional
        )
        bands = len(roi_values) // 2
        relevant_quality = [
            frame for frame in frames
            if frame.quality_reason != "insufficient_data" or frame is frames[-1]
        ]
        quality = _worst_quality(frame.quality for frame in relevant_quality)
        quality_reason = next(
            (
                frame.quality_reason for frame in reversed(relevant_quality)
                if frame.quality is quality and frame.quality_reason
            ),
            None,
        )
        end = frames[-1].timestamp_utc
        global_values = [
            float(frame.global_value) for frame in frames
            if frame.global_value is not None
        ]
        metric_names = sorted({
            name for frame in frames for name, _value in frame.metric_values
        })
        metric_values = {
            name: [
                float(value)
                for frame in frames
                for metric_name, value in frame.metric_values
                if metric_name == name and value is not None
            ]
            for name in metric_names
        }
        aggregated_metrics = {
            name: (median(values) if values else None)
            for name, values in metric_values.items()
        }
        # LuMon defines Aeration/MLI as the mean plethysmogram value over the
        # analysis interval. Keep it alongside the other calculated metrics.
        aggregated_metrics["mli_au"] = (
            sum(global_values) / len(global_values) if global_values else None
        )
        right_samples = [
            sum(float(value) for value in frame.roi_values[:bands] if value is not None)
            for frame in frames
            if bands and all(value is not None for value in frame.roi_values[:bands])
        ]
        left_samples = [
            sum(float(value) for value in frame.roi_values[bands:] if value is not None)
            for frame in frames
            if bands and all(value is not None for value in frame.roi_values[bands:])
        ]
        aggregate = TrendAggregate(
            study_id=study.id,
            session_id=session.id,
            interval_start_utc=frames[0].timestamp_utc,
            interval_end_utc=end,
            position_seconds=(
                frames[-1].position_seconds
                if frames[-1].position_seconds is not None
                else session.duration_seconds(end)
            ),
            aggregation_kind=kind,
            sample_count=len(frames),
            global_value=median(global_values) if global_values else None,
            right_value=median(right_samples) if right_samples else None,
            left_value=median(left_samples) if left_samples else None,
            roi_values=roi_values,
            respiratory_rate_bpm=frames[-1].respiratory_rate_bpm,
            metric_values=tuple(sorted(aggregated_metrics.items())),
            quality=quality,
            quality_reason=quality_reason,
            algorithm_version=TREND_ALGORITHM_VERSION,
            simulated=study.simulated,
        )
        self._repository.append(aggregate)


def _worst_quality(values) -> DataQuality:
    priority = {
        DataQuality.VALID: 0,
        DataQuality.DEGRADED: 1,
        DataQuality.STALE: 2,
        DataQuality.UNAVAILABLE: 3,
    }
    return max(values, key=priority.__getitem__, default=DataQuality.UNAVAILABLE)
