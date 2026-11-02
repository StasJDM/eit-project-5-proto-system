"""Durable time accounting for the current study and electrode system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Callable

from ..domain import utc_now
from .ports import SettingsRepository
from .studies import StudyLifecycleService


ELECTRODE_USAGE_SECONDS_SETTING = "electrode_system_usage_seconds"


@dataclass(frozen=True, slots=True)
class SessionClockSnapshot:
    eit_seconds: float = 0.0
    electrode_system_seconds: float = 0.0
    running: bool = False


class SessionClockService:
    """Uses persisted UTC intervals instead of incrementing display counters."""

    def __init__(
        self,
        lifecycle: StudyLifecycleService,
        settings: SettingsRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._lifecycle = lifecycle
        self._settings = settings
        self._clock = clock
        value = settings.load().get(ELECTRODE_USAGE_SECONDS_SETTING, 0.0)
        self._accumulated_es_seconds = _non_negative_seconds(value)
        self._es_started_at: datetime | None = None
        self._lock = RLock()

    @property
    def snapshot(self) -> SessionClockSnapshot:
        now = self._clock()
        session = self._lifecycle.current_session
        eit_seconds = session.duration_seconds(now) if session is not None else 0.0
        with self._lock:
            es_seconds = self._accumulated_es_seconds
            if self._es_started_at is not None:
                es_seconds += max(0.0, (now - self._es_started_at).total_seconds())
        return SessionClockSnapshot(
            eit_seconds=eit_seconds,
            electrode_system_seconds=es_seconds,
            running=self._lifecycle.is_running,
        )

    def start_electrode_usage(self) -> None:
        with self._lock:
            if self._es_started_at is None:
                self._es_started_at = self._clock()

    def stop_electrode_usage(self) -> None:
        with self._lock:
            if self._es_started_at is None:
                return
            now = self._clock()
            self._accumulated_es_seconds += max(
                0.0, (now - self._es_started_at).total_seconds()
            )
            self._es_started_at = None
            self._settings.save({
                ELECTRODE_USAGE_SECONDS_SETTING: self._accumulated_es_seconds
            })

    def close(self) -> None:
        self.stop_electrode_usage()


def _non_negative_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    number = float(value)
    return number if number >= 0.0 and number != float("inf") and number == number else 0.0
