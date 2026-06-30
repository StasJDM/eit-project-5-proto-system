"""Глобальные счётчики длительности ЭИТ и использования ЭС (мок-сессия)."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

# Типичная демо-сессия: мониторинг ~24 мин, накопленное время ЭС ~2 ч 16 мин
MOCK_EIT_START_S = 24 * 60 + 12          # 00:24:12
MOCK_ES_START_S = 2 * 3600 + 16 * 60 + 8  # 02:16:08


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
            cls._instance = SessionTimers(parent)
        return cls._instance

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._eit_s = MOCK_EIT_START_S
        self._es_s = MOCK_ES_START_S

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(1000)
        self._emit()

    def values(self) -> tuple[str, str]:
        return fmt_duration(self._eit_s), fmt_duration(self._es_s)

    def _on_tick(self):
        self._eit_s += 1
        self._es_s += 1
        self._emit()

    def _emit(self):
        self.updated.emit(*self.values())
