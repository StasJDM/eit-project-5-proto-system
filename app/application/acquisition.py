"""Background acquisition pipeline with bounded immutable snapshots."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Condition, Event, Lock, Thread
import time

from ..data_sources import (
    DataSource,
    DataSourceError,
    DataSourceSequenceError,
    DataSourceTimeoutError,
    FrameSequenceTracker,
    RawMeasurementFrame,
)
from ..domain import EITFrame


SourceFrame = EITFrame | RawMeasurementFrame


@dataclass(frozen=True, slots=True)
class AcquisitionMetrics:
    received_frames: int = 0
    dropped_frames: int = 0
    out_of_order_frames: int = 0
    buffer_overflows: int = 0
    queue_depth: int = 0
    queue_capacity: int = 0
    last_sequence_number: int | None = None
    last_latency_ms: float | None = None
    maximum_latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class AcquisitionSnapshot:
    frames: tuple[SourceFrame, ...]
    metrics: AcquisitionMetrics


class AcquisitionPipeline:
    def __init__(
        self,
        source: DataSource,
        *,
        capacity: int = 2250,
        frame_interval_seconds: float | None = None,
        on_frame: Callable[[SourceFrame], None] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if frame_interval_seconds is not None and frame_interval_seconds <= 0:
            raise ValueError("frame_interval_seconds must be positive")
        self._source = source
        self._capacity = capacity
        self._interval = frame_interval_seconds
        self._on_frame = on_frame
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._frames: deque[SourceFrame] = deque(maxlen=capacity)
        self._lock = Lock()
        self._condition = Condition(self._lock)
        self._stop = Event()
        self._thread: Thread | None = None
        self._sequence = FrameSequenceTracker()
        self._received = 0
        self._dropped = 0
        self._out_of_order = 0
        self._overflows = 0
        self._last_sequence: int | None = None
        self._last_latency_ms: float | None = None
        self._maximum_latency_ms = 0.0
        self._last_error: BaseException | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = Thread(
            target=self._run, name="eit-acquisition-pipeline", daemon=True
        )
        self._thread.start()

    def stop(self, timeout_seconds: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout_seconds)
        self._thread = None
        with self._condition:
            self._condition.notify_all()

    def snapshot(self) -> AcquisitionSnapshot:
        with self._lock:
            return AcquisitionSnapshot(tuple(self._frames), self._metrics_locked())

    def wait_for_received(self, minimum: int, timeout_seconds: float) -> AcquisitionSnapshot:
        if minimum < 0:
            raise ValueError("minimum must be non-negative")
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while self._received < minimum and self.is_running:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            return AcquisitionSnapshot(tuple(self._frames), self._metrics_locked())

    @property
    def last_error(self) -> BaseException | None:
        with self._lock:
            return self._last_error

    def _run(self) -> None:
        next_deadline = time.monotonic()
        while not self._stop.is_set():
            try:
                frame = self._source.read_frame()
                self._accept(frame)
            except DataSourceTimeoutError:
                continue
            except (DataSourceError, DataSourceSequenceError) as exc:
                with self._condition:
                    self._last_error = exc
                    self._condition.notify_all()
                return
            if self._interval is not None:
                next_deadline += self._interval
                self._stop.wait(max(0.0, next_deadline - time.monotonic()))

    def _accept(self, frame: SourceFrame) -> None:
        try:
            dropped = self._sequence.observe(frame.sequence_number)
        except DataSourceSequenceError:
            with self._lock:
                self._out_of_order += 1
            raise
        now = self._clock()
        if now.tzinfo is None:
            raise DataSourceError("acquisition clock must be timezone-aware")
        latency_ms = max(
            0.0,
            (now.astimezone(timezone.utc) - frame.timestamp_utc).total_seconds() * 1000.0,
        )
        with self._condition:
            if len(self._frames) == self._capacity:
                self._overflows += 1
            self._frames.append(frame)
            self._received += 1
            self._dropped += dropped
            self._last_sequence = frame.sequence_number
            self._last_latency_ms = latency_ms
            self._maximum_latency_ms = max(self._maximum_latency_ms, latency_ms)
            self._condition.notify_all()
        if self._on_frame is not None:
            self._on_frame(frame)

    def _metrics_locked(self) -> AcquisitionMetrics:
        return AcquisitionMetrics(
            received_frames=self._received,
            dropped_frames=self._dropped,
            out_of_order_frames=self._out_of_order,
            buffer_overflows=self._overflows,
            queue_depth=len(self._frames),
            queue_capacity=self._capacity,
            last_sequence_number=self._last_sequence,
            last_latency_ms=self._last_latency_ms,
            maximum_latency_ms=self._maximum_latency_ms,
        )
