"""Qt-independent contract for EIT data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from typing import TYPE_CHECKING

from ..config import DataMode
from ..domain import AcquisitionSettings, EITFrame

if TYPE_CHECKING:
    from .json_contract import RawMeasurementFrame


class DataSourceError(RuntimeError):
    """Base error raised by a data-source adapter."""


class DataSourceTimeoutError(DataSourceError):
    """No complete frame was received within the configured deadline."""


class DataSourceSequenceError(DataSourceError):
    """A duplicate, reversed or otherwise invalid sequence was observed."""


class DataSourceState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    CONFIGURED = "configured"
    RUNNING = "running"
    FAILED = "failed"


class DataSourceEventType(str, Enum):
    STATE_CHANGED = "state_changed"
    ERROR = "error"
    FRAME_GAP = "frame_gap"
    TIMEOUT = "timeout"


class TimestampSource(str, Enum):
    DEVICE = "device"
    RECORDING_METADATA = "recording_metadata"
    SYNTHESIZED = "synthesized"


@dataclass(frozen=True, slots=True)
class DeviceDescriptor:
    id: str
    name: str
    simulated: bool


@dataclass(frozen=True, slots=True)
class DataSourceTimingPolicy:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 0.2
    stale_after_seconds: float = 0.5
    max_consecutive_timeouts: int = 3
    reconnect_backoff_seconds: tuple[float, ...] = (0.25, 1.0, 2.0, 5.0)

    def __post_init__(self) -> None:
        numeric = (
            self.connect_timeout_seconds,
            self.read_timeout_seconds,
            self.stale_after_seconds,
            *self.reconnect_backoff_seconds,
        )
        if any(not math.isfinite(value) or value <= 0 for value in numeric):
            raise ValueError("data-source timeouts and backoff values must be positive")
        if self.max_consecutive_timeouts <= 0:
            raise ValueError("max_consecutive_timeouts must be positive")
        if self.stale_after_seconds < self.read_timeout_seconds:
            raise ValueError("stale_after_seconds must not precede read timeout")


@dataclass(frozen=True, slots=True)
class DataSourceEvent:
    type: DataSourceEventType
    occurred_at_utc: datetime
    state: DataSourceState
    message: str = ""
    expected_sequence: int | None = None
    received_sequence: int | None = None
    dropped_frames: int = 0
    recoverable: bool = True

    def __post_init__(self) -> None:
        if (
            self.occurred_at_utc.tzinfo is None
            or self.occurred_at_utc.utcoffset()
            != timezone.utc.utcoffset(self.occurred_at_utc)
        ):
            raise ValueError("data-source event timestamp must be UTC")
        if self.dropped_frames < 0:
            raise ValueError("dropped_frames must be non-negative")


class FrameSequenceTracker:
    """Enforces monotonic sequences and reports explicit frame loss."""

    def __init__(self, first_sequence: int = 0) -> None:
        if first_sequence < 0:
            raise ValueError("first_sequence must be non-negative")
        self._expected = first_sequence

    @property
    def expected(self) -> int:
        return self._expected

    def observe(self, sequence_number: int) -> int:
        if sequence_number < self._expected:
            raise DataSourceSequenceError(
                f"received sequence {sequence_number}, expected at least {self._expected}"
            )
        dropped = sequence_number - self._expected
        self._expected = sequence_number + 1
        return dropped


class DataSource(ABC):
    """Lifecycle shared by simulated and hardware EIT sources."""

    @property
    @abstractmethod
    def mode(self) -> DataMode:
        raise NotImplementedError

    @property
    @abstractmethod
    def state(self) -> DataSourceState:
        raise NotImplementedError

    @property
    def timing_policy(self) -> DataSourceTimingPolicy:
        return DataSourceTimingPolicy()

    def drain_events(self) -> tuple[DataSourceEvent, ...]:
        """Return pending source events in occurrence order and clear the queue."""
        return ()

    def electrode_contact_levels(self) -> tuple[float | None, ...] | None:
        """Return normalized contact quality for electrodes 1..16.

        ``None`` items represent technical errors. A source without a
        diagnostic channel returns ``None`` so the application fails safely.
        """
        return None

    @abstractmethod
    def discover(self) -> tuple[DeviceDescriptor, ...]:
        raise NotImplementedError

    @abstractmethod
    def connect(self, device_id: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def configure(self, settings: AcquisitionSettings) -> None:
        raise NotImplementedError

    @abstractmethod
    def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def reconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_frame(self) -> EITFrame | RawMeasurementFrame:
        raise NotImplementedError

