"""Persistent engineering-mode settings shared by UI and calculations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .events import ApplicationEvent, EventBus, EventType
from .ports import SettingsRepository


ENGINEERING_SETTINGS_KEY = "engineering_settings"
WORK_MODES = ("adult", "infant", "ventilation")
MIN_ROI_COUNT = 2
MAX_ROI_COUNT = 20
DEFAULT_ROI_COUNT = 8
PEAK_DETECTION_METHODS = ("derivative", "legacy")
DEFAULT_PEAK_DETECTION_METHOD = "derivative"


@dataclass(frozen=True, slots=True)
class EngineeringSettings:
    work_modes: tuple[str, ...] = ("adult",)
    roi_count: int = DEFAULT_ROI_COUNT
    peak_detection_method: str = DEFAULT_PEAK_DETECTION_METHOD

    def __post_init__(self) -> None:
        normalized = tuple(dict.fromkeys(self.work_modes))
        if not normalized:
            raise ValueError("at least one work mode must be enabled")
        if any(mode not in WORK_MODES for mode in normalized):
            raise ValueError("unsupported work mode")
        if normalized != self.work_modes:
            raise ValueError("work modes must be unique")
        if (
            isinstance(self.roi_count, bool)
            or not isinstance(self.roi_count, int)
            or not MIN_ROI_COUNT <= self.roi_count <= MAX_ROI_COUNT
            or self.roi_count % 2
        ):
            raise ValueError("roi_count must be an even integer from 2 to 20")
        if self.peak_detection_method not in PEAK_DETECTION_METHODS:
            raise ValueError("unsupported peak_detection_method")

    def to_payload(self) -> dict[str, object]:
        return {
            "work_modes": list(self.work_modes),
            "roi_count": self.roi_count,
            "peak_detection_method": self.peak_detection_method,
        }

    @classmethod
    def from_payload(cls, payload: object) -> "EngineeringSettings":
        if not isinstance(payload, dict):
            raise ValueError("stored engineering settings must be an object")
        modes = payload.get("work_modes", ["adult"])
        if not isinstance(modes, list) or not all(isinstance(item, str) for item in modes):
            raise ValueError("stored work_modes must be a string list")
        return cls(
            tuple(modes),
            payload.get("roi_count", DEFAULT_ROI_COUNT),
            payload.get("peak_detection_method", DEFAULT_PEAK_DETECTION_METHOD),
        )


class EngineeringSettingsService:
    def __init__(self, repository: SettingsRepository, event_bus: EventBus) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._listeners: list[Callable[[EngineeringSettings], None]] = []
        self._current = self._load()

    @property
    def current(self) -> EngineeringSettings:
        return self._current

    def save(self, settings: EngineeringSettings) -> EngineeringSettings:
        if not isinstance(settings, EngineeringSettings):
            raise TypeError("settings must be EngineeringSettings")
        self._repository.save({ENGINEERING_SETTINGS_KEY: settings.to_payload()})
        self._current = settings
        self._event_bus.publish(ApplicationEvent(
            EventType.SETTINGS_CHANGED,
            payload={ENGINEERING_SETTINGS_KEY: settings.to_payload()},
        ))
        for listener in tuple(self._listeners):
            listener(settings)
        return settings

    def subscribe(
        self, listener: Callable[[EngineeringSettings], None]
    ) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _load(self) -> EngineeringSettings:
        payload = self._repository.load().get(ENGINEERING_SETTINGS_KEY)
        return EngineeringSettings() if payload is None else EngineeringSettings.from_payload(payload)
