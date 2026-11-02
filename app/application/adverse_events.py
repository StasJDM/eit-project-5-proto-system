"""Durable append-only log of adverse and service events."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from .events import ApplicationEvent, EventBus, EventType
from .ports import EventRepository
from .studies import StudyLifecycleService
from ..domain import Event, EventCategory, StudyStatus, utc_now


ADVERSE_EVENT_TYPES = (
    "technical_error",
    "adverse_event",
    "adverse_phenomenon",
    "operator_note",
)


class AdverseEventError(RuntimeError):
    pass


class AdverseEventService:
    """Creates and queries clinical log entries without mutating originals."""

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
    def default_author(self) -> str:
        study = self._lifecycle.current_study
        return (study.author if study is not None else None) or "local-operator"

    def create(
        self,
        event_type: str,
        description: str,
        author: str,
        *,
        occurred_at_utc: datetime | None = None,
    ) -> Event:
        study, session = self._active_context()
        occurred = occurred_at_utc or self._clock()
        self._validate(event_type, description, author, occurred, session.started_at_utc)
        now = self._clock()
        event = Event(
            study_id=study.id,
            session_id=session.id,
            occurred_at_utc=occurred,
            category=EventCategory.ADVERSE_EVENT,
            text=description.strip(),
            event_type=event_type,
            author=author.strip(),
            position_seconds=max(0.0, session.duration_seconds(occurred)),
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
        study, _session = self._active_context()
        original = next(
            (item for item in self.list_current() if item.id == original_event_id), None
        )
        if original is None or original.category is not EventCategory.ADVERSE_EVENT:
            raise AdverseEventError("event does not exist in the current study")
        resolved_type = event_type or original.event_type
        self._validate(resolved_type, description, author, original.occurred_at_utc, None)
        now = self._clock()
        correction = Event(
            study_id=study.id,
            session_id=original.session_id,
            occurred_at_utc=original.occurred_at_utc,
            category=EventCategory.ADVERSE_EVENT,
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

    def list_current(
        self, *, start_utc=None, end_utc=None, query: str | None = None,
        include_markers: bool = True,
    ) -> tuple[Event, ...]:
        study = self._lifecycle.current_study
        if study is None:
            return ()
        events = self._repository.search(
            study.id, start_utc=start_utc, end_utc=end_utc, query=query
        )
        if include_markers:
            return tuple(events)
        return tuple(e for e in events if e.category is EventCategory.ADVERSE_EVENT)

    def _active_context(self):
        study = self._lifecycle.current_study
        session = self._lifecycle.current_session
        if study is None or session is None or study.status not in {
            StudyStatus.RUNNING, StudyStatus.PAUSED,
        }:
            raise AdverseEventError("an active monitoring session is required")
        return study, session

    def _validate(self, event_type, description, author, occurred, session_start):
        if event_type not in ADVERSE_EVENT_TYPES:
            raise AdverseEventError("unsupported adverse event type")
        if not description.strip():
            raise AdverseEventError("description must not be blank")
        if not author.strip():
            raise AdverseEventError("author must not be blank")
        if occurred.tzinfo is None:
            raise AdverseEventError("event date must be timezone-aware")
        if occurred > self._clock():
            raise AdverseEventError("event date must not be in the future")
        if session_start is not None and occurred < session_start:
            raise AdverseEventError("event date must not precede session start")

    def _publish(self, event: Event, action: str) -> None:
        self._event_bus.publish(ApplicationEvent(
            EventType.MARKERS_CHANGED,
            occurred_at_utc=event.created_at_utc,
            payload={"action": action, "study_id": str(event.study_id),
                     "event_id": str(event.id), "category": event.category.value},
        ))
