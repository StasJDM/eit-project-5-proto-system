"""Threaded adapter for the versioned EIT JSON-lines device protocol."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
from queue import Empty, Full, Queue
import socket
from threading import Event, Lock, Thread
from typing import Any, Protocol
from urllib.parse import urlparse

from ..config import DataMode
from ..domain import AcquisitionSettings, DataQuality
from .base import (
    DataSource, DataSourceError, DataSourceEvent, DataSourceEventType,
    DataSourceSequenceError, DataSourceState, DataSourceTimeoutError,
    DataSourceTimingPolicy, DeviceDescriptor, FrameSequenceTracker,
    TimestampSource,
)
from .json_contract import ADJACENT_16_PROTOCOL_ID, RawMeasurementFrame


PROTOCOL_NAME = "eit-json-stream"
PROTOCOL_VERSION = 1


class DeviceProtocolError(DataSourceError):
    """The peer returned malformed or incompatible protocol data."""


class DeviceTransport(Protocol):
    def send(self, payload: dict[str, Any]) -> None: ...
    def receive(self, timeout_seconds: float) -> dict[str, Any]: ...
    def close(self) -> None: ...


class JsonLineSocketTransport:
    """One UTF-8 JSON object per line over a TCP socket."""

    def __init__(self, endpoint: str, timeout_seconds: float) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "tcp" or not parsed.hostname or parsed.port is None:
            raise DataSourceError("device endpoint must be tcp://host:port")
        try:
            self._socket = socket.create_connection(
                (parsed.hostname, parsed.port), timeout=timeout_seconds
            )
        except OSError as exc:
            raise DataSourceError(f"cannot connect to EIT device: {exc}") from exc
        self._receive_buffer = bytearray()
        self._send_lock = Lock()

    def send(self, payload: dict[str, Any]) -> None:
        encoded = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
        )
        try:
            with self._send_lock:
                self._socket.sendall(encoded)
        except OSError as exc:
            raise DataSourceError(f"device write failed: {exc}") from exc

    def receive(self, timeout_seconds: float) -> dict[str, Any]:
        self._socket.settimeout(timeout_seconds)
        try:
            while b"\n" not in self._receive_buffer:
                block = self._socket.recv(65536)
                if not block:
                    raise DataSourceError("device disconnected")
                self._receive_buffer.extend(block)
                if len(self._receive_buffer) > 4 * 1024 * 1024:
                    raise DeviceProtocolError("device JSON line exceeds 4 MiB")
        except (TimeoutError, socket.timeout) as exc:
            raise DataSourceTimeoutError("device frame timeout") from exc
        except OSError as exc:
            raise DataSourceError(f"device read failed: {exc}") from exc
        line, _, remainder = self._receive_buffer.partition(b"\n")
        self._receive_buffer = bytearray(remainder)
        try:
            payload = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise DeviceProtocolError("device returned invalid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise DeviceProtocolError("device message must be a JSON object")
        return payload

    def close(self) -> None:
        self._socket.close()


TransportFactory = Callable[[str, float], DeviceTransport]


class DeviceDataSource(DataSource):
    """Hardware adapter with handshake, background reads and safe shutdown."""

    def __init__(
        self,
        endpoint: str | None,
        *,
        transport_factory: TransportFactory = JsonLineSocketTransport,
        timing_policy: DataSourceTimingPolicy | None = None,
        queue_capacity: int = 256,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if queue_capacity <= 0:
            raise ValueError("queue_capacity must be positive")
        self.endpoint = endpoint
        self._transport_factory = transport_factory
        self._timing_policy = timing_policy or DataSourceTimingPolicy()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._state = DataSourceState.DISCONNECTED
        self._transport: DeviceTransport | None = None
        self._settings: AcquisitionSettings | None = None
        self._frames: Queue[RawMeasurementFrame | BaseException] = Queue(queue_capacity)
        self._events: list[DataSourceEvent] = []
        self._events_lock = Lock()
        self._quality_lock = Lock()
        self._electrode_levels: tuple[float | None, ...] | None = None
        self._stop_event = Event()
        self._reader_thread: Thread | None = None
        self._sequence = FrameSequenceTracker()

    @property
    def mode(self) -> DataMode:
        return DataMode.DEVICE

    @property
    def state(self) -> DataSourceState:
        return self._state

    @property
    def timing_policy(self) -> DataSourceTimingPolicy:
        return self._timing_policy

    def drain_events(self) -> tuple[DataSourceEvent, ...]:
        with self._events_lock:
            result = tuple(self._events)
            self._events.clear()
        return result

    def electrode_contact_levels(self) -> tuple[float | None, ...] | None:
        with self._quality_lock:
            return self._electrode_levels

    def discover(self) -> tuple[DeviceDescriptor, ...]:
        if self.endpoint is None:
            return ()
        return (DeviceDescriptor(self.endpoint, "Configured EIT JSON device", False),)

    def connect(self, device_id: str | None = None) -> None:
        endpoint = device_id or self.endpoint
        if endpoint is None:
            self._set_state(DataSourceState.FAILED)
            raise self._error("EIT device endpoint is not configured", recoverable=False)
        if self._state is DataSourceState.RUNNING:
            raise self._error("cannot connect while device is running")
        self._transport = self._transport_factory(
            endpoint, self._timing_policy.connect_timeout_seconds
        )
        try:
            self._transport.send({
                "type": "hello", "protocol": PROTOCOL_NAME,
                "protocol_version": PROTOCOL_VERSION,
            })
            response = self._transport.receive(self._timing_policy.connect_timeout_seconds)
            self._expect_ack(response, "hello")
            if response.get("protocol") != PROTOCOL_NAME:
                raise DeviceProtocolError("incompatible EIT device protocol")
        except DataSourceError as exc:
            self._transport.close()
            self._transport = None
            self._set_state(DataSourceState.FAILED)
            self._emit(
                DataSourceEventType.ERROR,
                message=str(exc),
                recoverable=False,
            )
            raise
        self.endpoint = endpoint
        self._set_state(DataSourceState.CONNECTED)

    def disconnect(self) -> None:
        if self._state is DataSourceState.RUNNING:
            self.stop()
        self._stop_reader()
        if self._transport is not None:
            self._transport.close()
        self._transport = None
        self._settings = None
        self._clear_frames()
        self._set_state(DataSourceState.DISCONNECTED)

    def configure(self, settings: AcquisitionSettings) -> None:
        if self._state not in {DataSourceState.CONNECTED, DataSourceState.CONFIGURED}:
            raise self._error("connect the device before configuring it")
        transport = self._require_transport()
        transport.send({
            "type": "configure",
            "protocol_version": PROTOCOL_VERSION,
            "settings": {
                "current_ma": settings.injection_current_ma,
                "frequency_khz": settings.injection_frequency_khz,
                "electrode_count": settings.electrode_count,
                "belt_count": settings.belt_count,
                "frame_rate_hz": settings.sample_rate_hz,
                "measurement_protocol": ADJACENT_16_PROTOCOL_ID,
            },
        })
        self._expect_ack(
            transport.receive(self._timing_policy.connect_timeout_seconds),
            "configure",
        )
        self._settings = settings
        self._set_state(DataSourceState.CONFIGURED)

    def start(self) -> None:
        if self._state is not DataSourceState.CONFIGURED:
            raise self._error("configure the device before starting it")
        transport = self._require_transport()
        transport.send({"type": "start", "protocol_version": PROTOCOL_VERSION})
        self._expect_ack(
            transport.receive(self._timing_policy.connect_timeout_seconds), "start"
        )
        self._sequence = FrameSequenceTracker()
        self._clear_frames()
        self._stop_event.clear()
        self._set_state(DataSourceState.RUNNING)
        self._reader_thread = Thread(
            target=self._reader_loop, name="eit-device-reader", daemon=True
        )
        self._reader_thread.start()

    def stop(self) -> None:
        if self._state not in {DataSourceState.RUNNING, DataSourceState.FAILED}:
            return
        self._stop_reader()
        if self._transport is not None:
            try:
                self._transport.send({
                    "type": "stop", "protocol_version": PROTOCOL_VERSION
                })
            except DataSourceError:
                pass
        self._set_state(
            DataSourceState.CONFIGURED
            if self._transport is not None and self._settings is not None
            else DataSourceState.DISCONNECTED
        )

    def reconnect(self) -> None:
        settings = self._settings
        endpoint = self.endpoint
        self.disconnect()
        self.connect(endpoint)
        if settings is not None:
            self.configure(settings)

    def read_frame(self) -> RawMeasurementFrame:
        if self._state not in {DataSourceState.RUNNING, DataSourceState.FAILED}:
            raise self._error("device is not running")
        try:
            item = self._frames.get(timeout=self._timing_policy.read_timeout_seconds)
        except Empty as exc:
            raise DataSourceTimeoutError("device frame queue timeout") from exc
        if isinstance(item, BaseException):
            raise item
        return item

    def _reader_loop(self) -> None:
        consecutive_timeouts = 0
        while not self._stop_event.is_set():
            try:
                payload = self._require_transport().receive(
                    self._timing_policy.read_timeout_seconds
                )
                levels = _parse_electrode_quality(payload)
                if levels is not None:
                    with self._quality_lock:
                        self._electrode_levels = levels
                frame = _parse_live_frame(payload)
                dropped = self._sequence.observe(frame.sequence_number)
                if dropped:
                    self._emit(
                        DataSourceEventType.FRAME_GAP,
                        message="device frame gap",
                        expected_sequence=frame.sequence_number - dropped,
                        received_sequence=frame.sequence_number,
                        dropped_frames=dropped,
                    )
                self._frames.put(
                    frame, timeout=self._timing_policy.read_timeout_seconds
                )
                consecutive_timeouts = 0
            except DataSourceTimeoutError as exc:
                consecutive_timeouts += 1
                self._emit(DataSourceEventType.TIMEOUT, message=str(exc))
                if consecutive_timeouts < self._timing_policy.max_consecutive_timeouts:
                    continue
                self._reader_failed(exc)
                return
            except (DataSourceError, DataSourceSequenceError, Full) as exc:
                error = exc if isinstance(exc, DataSourceError) else DataSourceError(str(exc))
                self._reader_failed(error)
                return

    def _reader_failed(self, error: DataSourceError) -> None:
        self._state = DataSourceState.FAILED
        self._emit(DataSourceEventType.ERROR, message=str(error), recoverable=True)
        try:
            self._frames.put_nowait(error)
        except Full:
            pass

    def _stop_reader(self) -> None:
        self._stop_event.set()
        thread = self._reader_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._timing_policy.read_timeout_seconds * 2)
        self._reader_thread = None

    def _expect_ack(self, payload: dict[str, Any], command: str) -> None:
        if (
            payload.get("type") != "ack"
            or payload.get("command") != command
            or payload.get("protocol_version") != PROTOCOL_VERSION
        ):
            raise DeviceProtocolError(f"invalid {command} acknowledgement")

    def _require_transport(self) -> DeviceTransport:
        if self._transport is None:
            raise DataSourceError("device transport is not connected")
        return self._transport

    def _clear_frames(self) -> None:
        while True:
            try:
                self._frames.get_nowait()
            except Empty:
                return

    def _set_state(self, state: DataSourceState) -> None:
        self._state = state
        self._emit(DataSourceEventType.STATE_CHANGED)

    def _emit(self, event_type: DataSourceEventType, **details: Any) -> None:
        event = DataSourceEvent(
            type=event_type,
            occurred_at_utc=self._now(),
            state=self._state,
            **details,
        )
        with self._events_lock:
            self._events.append(event)

    def _error(self, message: str, *, recoverable: bool = True) -> DataSourceError:
        self._emit(DataSourceEventType.ERROR, message=message, recoverable=recoverable)
        return DataSourceError(message)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise DataSourceError("device clock must be timezone-aware")
        return value.astimezone(timezone.utc)


def _parse_live_frame(payload: dict[str, Any]) -> RawMeasurementFrame:
    if (
        payload.get("type") != "frame"
        or payload.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise DeviceProtocolError("unexpected device stream message")
    timestamp = payload.get("timestamp_utc")
    if not isinstance(timestamp, str):
        raise DeviceProtocolError("frame timestamp_utc must be ISO 8601")
    try:
        parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed_timestamp.tzinfo is None:
            raise ValueError("timestamp has no offset")
        timestamp_utc = parsed_timestamp.astimezone(timezone.utc)
        sequence_value = payload["sequence_number"]
        if isinstance(sequence_value, bool) or not isinstance(sequence_value, int):
            raise ValueError("sequence is not an integer")
        sequence = sequence_value
        channels = tuple(payload["channels"])
        quality = DataQuality(payload.get("quality", DataQuality.VALID.value))
    except (KeyError, TypeError, ValueError) as exc:
        raise DeviceProtocolError("malformed device frame") from exc
    try:
        return RawMeasurementFrame(
            sequence_number=sequence,
            timestamp_utc=timestamp_utc,
            channel_values=channels,
            protocol_id=str(payload.get("protocol_id", ADJACENT_16_PROTOCOL_ID)),
            belt_index=int(payload.get("belt_index", 0)),
            quality=quality,
            timestamp_source=TimestampSource.DEVICE,
            simulated=False,
        )
    except (TypeError, ValueError) as exc:
        raise DeviceProtocolError(f"invalid device frame: {exc}") from exc


def _parse_electrode_quality(
    payload: dict[str, Any],
) -> tuple[float | None, ...] | None:
    raw = payload.get("electrode_quality")
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != 16:
        raise DeviceProtocolError("electrode_quality must contain 16 values")
    result: list[float | None] = []
    for value in raw:
        if value is None:
            result.append(None)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DeviceProtocolError("electrode_quality values must be numeric or null")
        number = float(value)
        if not 0 <= number <= 1:
            raise DeviceProtocolError("electrode_quality values must be between 0 and 1")
        result.append(number)
    return tuple(result)
