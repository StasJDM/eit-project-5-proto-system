"""Application use case for read-only playback of completed studies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import UUID

from ..data_sources import (
    DataSource, DataSourceState, JSONMeasurementDataSource,
    RecordingPlaybackDataSource,
)
from ..domain import AcquisitionSettings, StudyStatus
from ..storage import AcquisitionRecordingStore
from .events import ApplicationEvent, EventBus, EventType
from .monitoring import MonitoringMode, MonitoringService
from .studies import StudyLifecycleService


class StudyPlaybackError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    active: bool = False
    paused: bool = False
    study_id: UUID | None = None
    session_id: UUID | None = None
    position_seconds: float = 0.0
    duration_seconds: float = 0.0
    speed: float = 1.0
    read_only: bool = False


class StudyPlaybackService:
    """Switch monitoring screens between the live and recorded sources."""

    def __init__(
        self,
        store: AcquisitionRecordingStore,
        monitoring: MonitoringService,
        lifecycle: StudyLifecycleService,
        event_bus: EventBus,
        *,
        live_source: DataSource,
        live_settings_provider: Callable[[], AcquisitionSettings],
    ) -> None:
        self._store = store
        self._monitoring = monitoring
        self._lifecycle = lifecycle
        self._event_bus = event_bus
        self._live_source = live_source
        self._live_settings_provider = live_settings_provider
        self._source: RecordingPlaybackDataSource | JSONMeasurementDataSource | None = None

    @property
    def snapshot(self) -> PlaybackSnapshot:
        source = self._source
        if source is None:
            return PlaybackSnapshot(active=False)
        return PlaybackSnapshot(
            active=True,
            paused=source.state is not DataSourceState.RUNNING,
            study_id=getattr(source, "study_id", None),
            session_id=getattr(source, "session_id", None),
            position_seconds=source.position_seconds,
            duration_seconds=source.duration_seconds,
            speed=source.playback_speed,
            read_only=True,
        )

    def open(self, study_id: UUID, session_id: UUID, *, speed: float = 1.0) -> None:
        study = self._lifecycle.open_study(study_id)
        session = self._lifecycle.current_session
        if study.status is not StudyStatus.COMPLETED:
            raise StudyPlaybackError("only a completed study can be played back")
        if session is None or session.id != session_id or session.study_id != study.id:
            raise StudyPlaybackError("recording session does not belong to the study")
        source = RecordingPlaybackDataSource(
            self._store, study.id, session.id, playback_speed=speed
        )
        self._monitoring.replace_source(
            source, study.settings, mode=MonitoringMode.PLAYBACK
        )
        self._source = source
        self._publish()

    def open_json(self, path: str | Path, *, speed: float = 1.0) -> None:
        """Backward-compatible alias for :meth:`open_file`."""
        self.open_file(path, speed=speed)

    def open_file(self, path: str | Path, *, speed: float = 1.0) -> None:
        """Open an external JSON, CSV or XLSX recording for reconstruction."""
        source = JSONMeasurementDataSource(path, playback_speed=speed)
        self._monitoring.replace_source(
            source,
            source.suggested_settings,
            mode=MonitoringMode.PLAYBACK,
        )
        self._source = source
        self._publish()

    def seek(self, seconds: float) -> float:
        self._require_active()
        position = self._monitoring.seek_playback(seconds)
        self._publish()
        return position

    def set_speed(self, speed: float) -> None:
        self._require_active()
        self._monitoring.set_playback_speed(speed)
        self._publish()

    def pause(self) -> None:
        self._require_active()
        self._monitoring.pause_playback()
        self._publish()

    def resume(self) -> None:
        self._require_active()
        self._monitoring.resume_playback()
        self._publish()

    def close(self) -> None:
        if self._source is None:
            return
        self._source = None
        self._monitoring.replace_source(
            self._live_source,
            self._live_settings_provider(),
            mode=MonitoringMode.LIVE,
            start=False,
        )
        self._publish()

    def _require_active(
        self,
    ) -> RecordingPlaybackDataSource | JSONMeasurementDataSource:
        if self._source is None:
            raise StudyPlaybackError("no study recording is open")
        return self._source

    def _publish(self) -> None:
        state = self.snapshot
        self._event_bus.publish(ApplicationEvent(
            EventType.PLAYBACK_CHANGED,
            payload={
                "active": state.active,
                "paused": state.paused,
                "study_id": str(state.study_id) if state.study_id else None,
                "session_id": str(state.session_id) if state.session_id else None,
                "position_seconds": state.position_seconds,
                "duration_seconds": state.duration_seconds,
                "speed": state.speed,
                "read_only": state.read_only,
            },
        ))
