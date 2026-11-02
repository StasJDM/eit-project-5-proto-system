"""Shared UI counters synchronized with the current monitoring session."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal
from .application.session_clock import SessionClockService


def fmt_duration(total_s: int) -> str:
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class SessionTimers(QObject):
    """Singleton: единый источник времени для всех экранов."""

    updated = Signal(str, str)  # eit_str, es_str

    _instance: SessionTimers | None = None

    @classmethod
    def instance(cls, parent: QObject | None = None) -> SessionTimers:
        if cls._instance is None:
            # The shared timer must outlive individual windows. Parenting it to
            # the first MainWindow leaves a dangling Python singleton after
            # that window is closed and another one is created.
            application = QCoreApplication.instance()
            cls._instance = SessionTimers(application or parent)
        return cls._instance

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._service: SessionClockService | None = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(1000)
        self._emit()

    def values(self) -> tuple[str, str]:
        if self._service is None:
            return fmt_duration(0), fmt_duration(0)
        snapshot = self._service.snapshot
        return (
            fmt_duration(int(snapshot.eit_seconds)),
            fmt_duration(int(snapshot.electrode_system_seconds)),
        )

    def _on_tick(self):
        self._emit()

    def bind(self, service: SessionClockService | None) -> None:
        self._service = service
        self._emit()

    def _emit(self):
        self.updated.emit(*self.values())
