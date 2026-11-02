"""Persistent, validated EIT acquisition settings."""

from __future__ import annotations

from ..domain import AcquisitionSettings, deserialize_model, serialize_model
from .events import ApplicationEvent, EventBus, EventType
from .ports import SettingsRepository


ACQUISITION_SETTINGS_KEY = "eit_acquisition_settings"


class EITSettingsService:
    def __init__(self, repository: SettingsRepository, event_bus: EventBus) -> None:
        self._repository = repository
        self._event_bus = event_bus

    @property
    def current(self) -> AcquisitionSettings:
        payload = self._repository.load().get(ACQUISITION_SETTINGS_KEY)
        if payload is None:
            return AcquisitionSettings()
        if not isinstance(payload, dict):
            raise ValueError("stored EIT settings must be an object")
        settings = deserialize_model(payload)
        if not isinstance(settings, AcquisitionSettings):
            raise ValueError("stored EIT settings have an unexpected model type")
        return settings

    def save(self, settings: AcquisitionSettings) -> AcquisitionSettings:
        if not isinstance(settings, AcquisitionSettings):
            raise TypeError("settings must be AcquisitionSettings")
        self._repository.save({ACQUISITION_SETTINGS_KEY: serialize_model(settings)})
        self._event_bus.publish(ApplicationEvent(
            EventType.SETTINGS_CHANGED,
            payload={ACQUISITION_SETTINGS_KEY: serialize_model(settings)},
        ))
        return settings

    def reset(self) -> AcquisitionSettings:
        return self.save(AcquisitionSettings())
