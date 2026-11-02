"""Small synchronous event bus shared by application services and adapters."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any


class EventType(str, Enum):
    DATA_SOURCE_STATE_CHANGED = "data_source.state_changed"
    FRAME_RECEIVED = "monitoring.frame_received"
    APPLICATION_ERROR = "application.error"
    SETTINGS_CHANGED = "settings.changed"
    STUDY_CHANGED = "study.changed"
    PLAYBACK_CHANGED = "playback.changed"
    ELECTRODE_QUALITY_CHANGED = "electrode_quality.changed"
    CALIBRATION_CHANGED = "calibration.changed"
    MONITORING_SESSION_CHANGED = "monitoring_session.changed"
    MARKERS_CHANGED = "markers.changed"


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    type: EventType
    occurred_at_utc: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.occurred_at_utc.tzinfo is None:
            raise ValueError("event timestamp must be timezone-aware")


EventHandler = Callable[[ApplicationEvent], None]


class EventBus:
    """Process-local event transport with deterministic subscription order."""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_type: EventType, handler: EventHandler) -> Callable[[], None]:
        with self._lock:
            self._handlers[event_type].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                handlers = self._handlers[event_type]
                if handler in handlers:
                    handlers.remove(handler)

        return unsubscribe

    def publish(self, event: ApplicationEvent) -> None:
        with self._lock:
            handlers = tuple(self._handlers[event.type])
        for handler in handlers:
            handler(event)
