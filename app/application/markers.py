"""Append-only event markers bound to an exact monitoring-session position."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from ..domain import Event, EventCategory, StudyStatus, utc_now
from .events import ApplicationEvent, EventBus, EventType
from .ports import EventRepository
from .studies import StudyLifecycleService


MARKER_TYPES = (
    "cough",
    "procedure",
    "position_change",
    "suction",
    "operator_note",
)


class EventMarkerError(RuntimeError):
    pass


class EventMarkerService:
    """Creates durable markers and corrections without mutating history."""

    def __init__(
        self,
        repository: EventRepository,
        lifecycle: StudyLifecycleService,
        event_bus: EventBus,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._lifecycle = lifecycle
        self._event_bus = event_bus
        self._clock = clock

    @property
    def current_position_seconds(self) -> float:
        session = self._lifecycle.current_session
        if session is None or session.started_at_utc is None:
            return 0.0
        return session.duration_seconds(self._clock())

    @property
    def default_author(self) -> str:
        study = self._lifecycle.current_study
        return (study.author if study is not None else None) or "local-operator"

    @property
    def has_current_study(self) -> bool:
        return self._lifecycle.current_study is not None

    def create(self, event_type: str, description: str, author: str) -> Event:
        study, session = self._active_context()
        self._validate_input(event_type, description, author)
        now = self._clock()
        event = Event(
            study_id=study.id,
            session_id=session.id,
            occurred_at_utc=now,
            category=EventCategory.MARKER,
            text=description.strip(),
            event_type=event_type,
            author=author.strip(),
            position_seconds=session.duration_seconds(now),
            simulated=study.simulated,
            created_at_utc=now,
        )
        self._repository.append(study.id, event)
        self._publish(event, "created")
        return event

    def correct(
        self,
        original_event_id: UUID,
        description: str,
        author: str,
        *,
        event_type: str | None = None,
    ) -> Event:
        study = self._lifecycle.current_study
        session = self._lifecycle.current_session
        if study is None or session is None:
            raise EventMarkerError("no study is selected")
        original = next(
            (item for item in self.list_for_current_study() if item.id == original_event_id),
            None,
        )
        if original is None or original.category is not EventCategory.MARKER:
            raise EventMarkerError("marker does not exist in the current study")
        resolved_type = event_type or original.event_type
        self._validate_input(resolved_type, description, author)
        now = self._clock()
        correction = Event(
            study_id=study.id,
            session_id=original.session_id,
            occurred_at_utc=now,
            category=EventCategory.MARKER,
            text=description.strip(),
            event_type=resolved_type,
            author=author.strip(),
            position_seconds=original.position_seconds,
            corrects_event_id=original.id,
            simulated=study.simulated,
            created_at_utc=now,
        )
        self._repository.append(study.id, correction)
        self._publish(correction, "corrected")
        return correction

    def list_for_current_study(self) -> tuple[Event, ...]:
        study = self._lifecycle.current_study
        if study is None:
            return ()
        return tuple(
            item for item in self._repository.list_for_study(study.id)
            if item.category is EventCategory.MARKER
        )

    def markers_between(self, start_seconds: float, end_seconds: float) -> tuple[Event, ...]:
        if end_seconds < start_seconds:
            return ()
        return tuple(
            item for item in self.list_for_current_study()
            if start_seconds <= item.position_seconds <= end_seconds
        )

    def _active_context(self):
        study = self._lifecycle.current_study
        session = self._lifecycle.current_session
        if (
            study is None
            or session is None
            or study.status not in {StudyStatus.RUNNING, StudyStatus.PAUSED}
        ):
            raise EventMarkerError("an active monitoring session is required")
        return study, session

    @staticmethod
    def _validate_input(event_type: str, description: str, author: str) -> None:
        if event_type not in MARKER_TYPES:
            raise EventMarkerError("unsupported marker type")
        if not description.strip():
            raise EventMarkerError("marker description must not be blank")
        if not author.strip():
            raise EventMarkerError("marker author must not be blank")

    def _publish(self, event: Event, action: str) -> None:
        self._event_bus.publish(ApplicationEvent(
            EventType.MARKERS_CHANGED,
            occurred_at_utc=event.created_at_utc,
            payload={
                "action": action,
                "study_id": str(event.study_id),
                "event_id": str(event.id),
                "position_seconds": event.position_seconds,
                "corrects_event_id": (
                    str(event.corrects_event_id) if event.corrects_event_id else None
                ),
            },
        ))
