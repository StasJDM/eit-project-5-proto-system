"""Coordinates study lifecycle with crash-safe acquisition recording."""

from __future__ import annotations

from threading import RLock

from ..domain import StudyStatus
from ..storage.recording import AcquisitionRecordingStore, AcquisitionRecordingWriter
from .acquisition import SourceFrame
from .events import ApplicationEvent, EventBus, EventType
from .monitoring import MonitoringService
from .studies import StudyLifecycleService


class StudyRecordingService:
    def __init__(
        self,
        store: AcquisitionRecordingStore,
        monitoring: MonitoringService,
        lifecycle: StudyLifecycleService,
        event_bus: EventBus,
    ) -> None:
        self._store = store
        self._monitoring = monitoring
        self._lifecycle = lifecycle
        self._writer: AcquisitionRecordingWriter | None = None
        self._lock = RLock()
        self.recovered_manifests = store.recover_incomplete()
        self._unsubscribe_study = event_bus.subscribe(
            EventType.STUDY_CHANGED, self._on_study_changed
        )
        self._unsubscribe_frames = monitoring.subscribe_frames(self._on_frame)

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._writer is not None

    def close(self) -> None:
        self._unsubscribe_study()
        self._unsubscribe_frames()
        with self._lock:
            if self._writer is not None:
                self._writer.close(completed=False)
                self._writer = None

    def _on_study_changed(self, _event: ApplicationEvent) -> None:
        study = self._lifecycle.current_study
        session = self._lifecycle.current_session
        with self._lock:
            if (
                study is not None
                and session is not None
                and study.status in {StudyStatus.RUNNING, StudyStatus.PAUSED}
                and self._writer is None
            ):
                self._writer = self._store.open_writer(
                    study.id,
                    session.id,
                    frame_rate_hz=study.settings.sample_rate_hz,
                )
            elif (
                self._writer is not None
                and (study is None or study.status in {StudyStatus.COMPLETED, StudyStatus.FAILED})
            ):
                self._writer.close(
                    completed=study is not None and study.status is StudyStatus.COMPLETED
                )
                self._writer = None

    def _on_frame(self, frame: SourceFrame) -> None:
        if self._lifecycle.status is not StudyStatus.RUNNING:
            return
        with self._lock:
            if self._writer is not None:
                self._writer.append(frame)
