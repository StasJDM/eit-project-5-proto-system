"""Incremental persistence and range reads for long-running trend data."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from collections.abc import Callable
from threading import RLock
from uuid import UUID

from .events import ApplicationEvent, EventBus, EventType
from .monitoring import MonitoringService, TrendSample
from .ports import TrendRepository
from .trend_buffer import TrendWindow
from .studies import StudyLifecycleService
from ..domain import StudyStatus, TrendAggregate, utc_now


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
        hidden_metrics_provider: Callable[[], tuple[str, ...]] | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._repository = repository
        self._monitoring = monitoring
        self._lifecycle = lifecycle
        self._interval_seconds = float(interval_seconds)
        self._clock = clock
        self._hidden_metrics_provider = hidden_metrics_provider or (lambda: ())
        self._position_session_id: UUID | None = None
        self._source_time_origin: datetime | None = None
        self._source_position_origin = 0.0
        self._lock = RLock()
        self._interval_frames = TrendWindow()
        self._cycle_frames = TrendWindow()
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

    @property
    def change_token(self):
        return getattr(self._repository, "change_token", None)

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
                frame.timestamp_utc - self._interval_frames.first.timestamp_utc
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
                self._cycle_frames.clear()
                self._cycle_frames.append(frame)

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

    def _flush_frames(self, frames: TrendWindow, kind: str) -> None:
        study = self._lifecycle.current_study
        session = self._lifecycle.current_session
        if not frames or study is None or session is None or session.started_at_utc is None:
            return
        hidden_metrics = set(self._hidden_metrics_provider())
        last = frames.last
        quality, quality_reason = frames.quality()
        aggregated_metrics = {
            name: frames.median(f"metric:{name}")
            for name in frames.metric_names if name not in hidden_metrics
        }
        if "mli_au" not in hidden_metrics:
            aggregated_metrics["mli_au"] = frames.mean_global()
        right_value, left_value = frames.side_medians()
        roi_values = tuple(
            frames.median(f"roi:{i}")
            if (f"roi_{i + 1}_tvi_au" not in hidden_metrics
                or f"roi_{i + 1}_percent" not in hidden_metrics)
            else None
            for i in range(frames.roi_count)
        )
        aggregate = TrendAggregate(
            study_id=study.id,
            session_id=session.id,
            interval_start_utc=frames.first.timestamp_utc,
            interval_end_utc=last.timestamp_utc,
            position_seconds=(
                last.position_seconds
                if last.position_seconds is not None
                else session.duration_seconds(last.timestamp_utc)
            ),
            aggregation_kind=kind,
            sample_count=len(frames),
            global_value=frames.median("global"),
            right_value=right_value if "right_percent" not in hidden_metrics else None,
            left_value=left_value if "left_percent" not in hidden_metrics else None,
            roi_values=roi_values,
            respiratory_rate_bpm=(
                last.respiratory_rate_bpm
                if "rr_bpm" not in hidden_metrics
                else None
            ),
            metric_values=tuple(sorted(aggregated_metrics.items())),
            quality=quality,
            quality_reason=quality_reason,
            algorithm_version=TREND_ALGORITHM_VERSION,
            simulated=study.simulated,
        )
        self._repository.append(aggregate)
