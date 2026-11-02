"""Single transactional controller for an application's monitoring session."""

from __future__ import annotations

from threading import RLock

from ..domain import StudyStatus
from .events import ApplicationEvent, EventBus, EventType
from .monitoring import MonitoringService
from .session_clock import SessionClockService
from .studies import InvalidStudyTransition, StudyLifecycleError, StudyLifecycleService


class MonitoringControllerError(StudyLifecycleError):
    pass


class MonitoringController:
    """Coordinates lifecycle, acquisition, recording subscribers and counters."""

    def __init__(
        self,
        lifecycle: StudyLifecycleService,
        monitoring: MonitoringService,
        clock: SessionClockService,
        event_bus: EventBus,
    ) -> None:
        self._lifecycle = lifecycle
        self._monitoring = monitoring
        self._clock = clock
        self._event_bus = event_bus
        self._lock = RLock()
        self._transitioning = False

    @property
    def status(self) -> StudyStatus | None:
        return self._lifecycle.status

    @property
    def is_running(self) -> bool:
        return self.status is StudyStatus.RUNNING and self._monitoring.is_running

    def start(self) -> None:
        with self._transition():
            if self.status is StudyStatus.PAUSED:
                self._resume_locked()
                return
            if self.status is not StudyStatus.READY:
                raise InvalidStudyTransition("only a ready study can be started")
            try:
                self._preflight_diagnostics()
                # The lifecycle event opens the recording writer synchronously.
                self._lifecycle.start()
                self._monitoring.start()
                self._clock.start_electrode_usage()
            except StudyLifecycleError:
                self._monitoring.stop()
                self._clock.stop_electrode_usage()
                self._publish("start_rejected")
                raise
            except Exception as exc:
                self._monitoring.stop()
                self._clock.stop_electrode_usage()
                if self.status in {StudyStatus.RUNNING, StudyStatus.PAUSED}:
                    self._lifecycle.fail(reason="monitoring_start_failed")
                self._publish("start_failed", error=type(exc).__name__)
                raise MonitoringControllerError("monitoring start failed") from exc
            self._publish("started")

    def pause(self) -> None:
        with self._transition():
            if self.status is not StudyStatus.RUNNING:
                raise InvalidStudyTransition("only a running study can be paused")
            try:
                self._monitoring.suspend()
                self._lifecycle.pause()
                self._clock.stop_electrode_usage()
            except Exception as exc:
                self._monitoring.stop()
                self._clock.stop_electrode_usage()
                if self.status in {StudyStatus.RUNNING, StudyStatus.PAUSED}:
                    self._lifecycle.fail(reason="monitoring_pause_failed")
                self._publish("pause_failed", error=type(exc).__name__)
                raise MonitoringControllerError("monitoring pause failed") from exc
            self._publish("paused")

    def resume(self) -> None:
        with self._transition():
            self._resume_locked()

    def stop(self, *, conclusion: str | None = None) -> None:
        with self._transition():
            if self.status not in {StudyStatus.RUNNING, StudyStatus.PAUSED}:
                raise InvalidStudyTransition("only an active study can be completed")
            try:
                # The lifecycle event closes the writer before acquisition is
                # torn down, so every accepted frame is durably finalized.
                self._lifecycle.stop(conclusion=conclusion)
            finally:
                self._monitoring.stop()
                self._clock.stop_electrode_usage()
            self._publish("stopped")

    def shutdown(self) -> None:
        with self._lock:
            if self.status in {StudyStatus.RUNNING, StudyStatus.PAUSED}:
                self.stop(conclusion="application_closed")
            else:
                self._monitoring.stop()
                self._clock.close()

    def _resume_locked(self) -> None:
        if self.status is not StudyStatus.PAUSED:
            raise InvalidStudyTransition("only a paused study can be resumed")
        self._lifecycle.resume()
        try:
            self._monitoring.resume()
            self._clock.start_electrode_usage()
        except Exception as exc:
            self._lifecycle.fail(reason="monitoring_resume_failed")
            self._monitoring.stop()
            self._clock.stop_electrode_usage()
            self._publish("resume_failed", error=type(exc).__name__)
            raise MonitoringControllerError("monitoring resume failed") from exc
        self._publish("resumed")

    def _preflight_diagnostics(self) -> None:
        if self._monitoring.source.electrode_contact_levels() is not None:
            return
        try:
            self._monitoring.start()
            self._monitoring.prime(1)
        finally:
            self._monitoring.stop()

    def _publish(self, action: str, **payload: str) -> None:
        self._event_bus.publish(ApplicationEvent(
            EventType.MONITORING_SESSION_CHANGED,
            payload={"action": action, "status": self.status.value if self.status else None} | payload,
        ))

    class _Transition:
        def __init__(self, owner: "MonitoringController") -> None:
            self.owner = owner

        def __enter__(self):
            self.owner._lock.acquire()
            if self.owner._transitioning:
                self.owner._lock.release()
                raise MonitoringControllerError("monitoring transition is already in progress")
            self.owner._transitioning = True

        def __exit__(self, exc_type, exc, traceback):
            self.owner._transitioning = False
            self.owner._lock.release()

    def _transition(self) -> "MonitoringController._Transition":
        return self._Transition(self)
