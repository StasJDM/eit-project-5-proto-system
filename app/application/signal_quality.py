"""Electrode contact diagnostics and study calibration workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable

from ..config import DataMode
from ..domain import CalibrationRecord, CalibrationStatus, utc_now
from .events import ApplicationEvent, EventBus, EventType
from .monitoring import MonitoringService
from .studies import StudyLifecycleError, StudyLifecycleService


ELECTRODE_COUNT = 16
USABLE_LEVEL = 0.50
INSUFFICIENT_LEVEL = 0.30
STRONG_LEVEL = 0.70
MINIMUM_USABLE_RATIO = 0.80


class ElectrodeContactStatus(str, Enum):
    STRONG = "strong"
    ADEQUATE = "adequate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"
    TECHNICAL_ERROR = "technical_error"


class ElectrodeQualityBlockedError(StudyLifecycleError):
    pass


@dataclass(frozen=True, slots=True)
class ElectrodeContact:
    number: int
    level: float | None
    status: ElectrodeContactStatus


@dataclass(frozen=True, slots=True)
class ElectrodeQualitySnapshot:
    contacts: tuple[ElectrodeContact, ...]
    measured_at_utc: datetime
    usable_measurement_ratio: float
    start_allowed: bool
    reason: str | None = None

    @property
    def levels(self) -> tuple[float | None, ...]:
        return tuple(item.level for item in self.contacts)


class ElectrodeQualityService:
    def __init__(
        self,
        monitoring: MonitoringService,
        lifecycle: StudyLifecycleService,
        event_bus: EventBus,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._monitoring = monitoring
        self._lifecycle = lifecycle
        self._event_bus = event_bus
        self._clock = clock
        self._snapshot: ElectrodeQualitySnapshot | None = None
        self._last_calibration: CalibrationRecord | None = None

    @property
    def snapshot(self) -> ElectrodeQualitySnapshot:
        return self._snapshot or self.refresh()

    @property
    def last_calibration(self) -> CalibrationRecord | None:
        study = self._lifecycle.current_study
        return study.calibration if study is not None else self._last_calibration

    def refresh(self) -> ElectrodeQualitySnapshot:
        raw = self._monitoring.source.electrode_contact_levels()
        levels: tuple[float | None, ...]
        if raw is None:
            levels = (None,) * ELECTRODE_COUNT
        else:
            if len(raw) != ELECTRODE_COUNT:
                raise ValueError("electrode contact source must return 16 values")
            levels = tuple(raw)
        contacts = tuple(
            ElectrodeContact(index + 1, value, _classify(value))
            for index, value in enumerate(levels)
        )
        usable = sum(
            item.level is not None and item.level >= USABLE_LEVEL for item in contacts
        )
        ratio = usable / ELECTRODE_COUNT
        technical = tuple(
            item.number
            for item in contacts
            if item.status is ElectrodeContactStatus.TECHNICAL_ERROR
        )
        allowed = ratio >= MINIMUM_USABLE_RATIO and not technical
        reason = None
        if technical:
            reason = "technical_error:" + ",".join(map(str, technical))
        elif ratio < MINIMUM_USABLE_RATIO:
            reason = "usable_measurement_ratio_below_0.80"
        snapshot = ElectrodeQualitySnapshot(
            contacts=contacts,
            measured_at_utc=self._clock(),
            usable_measurement_ratio=ratio,
            start_allowed=allowed,
            reason=reason,
        )
        previous = self._snapshot
        self._snapshot = snapshot
        changed = tuple(
            item.number
            for index, item in enumerate(contacts)
            if previous is None or previous.contacts[index].status is not item.status
        )
        if changed:
            self._event_bus.publish(ApplicationEvent(
                EventType.ELECTRODE_QUALITY_CHANGED,
                occurred_at_utc=snapshot.measured_at_utc,
                payload={
                    "electrodes": changed,
                    "usable_measurement_ratio": ratio,
                    "start_allowed": allowed,
                    "reason": reason,
                },
            ))
        return snapshot

    def calibrate(self) -> CalibrationRecord:
        study = self._lifecycle.current_study
        if study is None:
            raise StudyLifecycleError("prepare a study before calibration")
        snapshot = self.refresh()
        failed = tuple(
            item.number
            for item in snapshot.contacts
            if item.status in {
                ElectrodeContactStatus.INSUFFICIENT,
                ElectrodeContactStatus.TECHNICAL_ERROR,
            }
        )
        result = CalibrationRecord(
            performed_at_utc=self._clock(),
            status=(
                CalibrationStatus.SUCCEEDED
                if snapshot.start_allowed else CalibrationStatus.FAILED
            ),
            usable_measurement_ratio=snapshot.usable_measurement_ratio,
            electrode_levels=snapshot.levels,
            failed_electrodes=failed,
            reason=snapshot.reason,
            simulated=study.simulated,
        )
        self._lifecycle.save_calibration(result)
        self._last_calibration = result
        self._event_bus.publish(ApplicationEvent(
            EventType.CALIBRATION_CHANGED,
            occurred_at_utc=result.performed_at_utc,
            payload={
                "study_id": str(study.id),
                "status": result.status.value,
                "reason": result.reason,
                "failed_electrodes": result.failed_electrodes,
            },
        ))
        return result

    def ensure_start_allowed(self) -> None:
        # A file recording has no live electrode-contact channel. Its frames
        # were acquired earlier, so the hardware preflight is not applicable
        # during read-only/demo reproduction. Device mode still fails safely
        # when diagnostics are absent, and simulation keeps exercising the
        # normal contact-quality policy.
        if self._monitoring.source.mode is DataMode.FROMFILE:
            return
        snapshot = self.refresh()
        if not snapshot.start_allowed:
            raise ElectrodeQualityBlockedError(
                snapshot.reason or "electrode contact quality is insufficient"
            )


def _classify(level: float | None) -> ElectrodeContactStatus:
    if level is None or level <= 0:
        return ElectrodeContactStatus.TECHNICAL_ERROR
    if level >= STRONG_LEVEL:
        return ElectrodeContactStatus.STRONG
    if level >= USABLE_LEVEL:
        return ElectrodeContactStatus.ADEQUATE
    if level >= INSUFFICIENT_LEVEL:
        return ElectrodeContactStatus.WEAK
    return ElectrodeContactStatus.INSUFFICIENT
