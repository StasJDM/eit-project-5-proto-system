"""Read-only playback adapter for crash-safe study recordings."""

from __future__ import annotations

from array import array
from bisect import bisect_left, bisect_right
import math
from threading import RLock
from typing import TYPE_CHECKING, TypeAlias
from uuid import UUID

from ..config import DataMode
from ..domain import AcquisitionSettings, EITFrame
from .base import DataSource, DataSourceError, DataSourceState, DeviceDescriptor
from .json_contract import RawMeasurementFrame

if TYPE_CHECKING:
    from ..storage.recording import AcquisitionRecordingStore

SourceFrame: TypeAlias = EITFrame | RawMeasurementFrame


class RecordingPlaybackComplete(DataSourceError):
    """The last confirmed frame of a recording has been delivered."""


class RecordingPlaybackDataSource(DataSource):
    """Expose a completed recording through the normal data-source contract.

    The adapter deliberately has no write operation. Frames are immutable domain
    objects loaded through ``AcquisitionRecordingStore``, which verifies every
    chunk checksum before playback starts.
    """

    is_playback = True

    def __init__(
        self,
        store: AcquisitionRecordingStore,
        study_id: UUID,
        session_id: UUID,
        *,
        playback_speed: float = 1.0,
    ) -> None:
        self._store = store
        self.study_id = study_id
        self.session_id = session_id
        self._metadata = store.metadata(study_id, session_id)
        if self._metadata.status != "completed":
            raise DataSourceError("only completed recordings can be played back")
        self._chunks = []
        self._chunk_starts = []
        self._elapsed = array("d")
        self._loaded_chunk = None
        self._chunk_frames = []
        origin = None
        # Validate the entire recording first, retaining only its seek index.
        for chunk, frames in store.iter_chunks(study_id, session_id):
            if frames:
                if origin is None:
                    origin = frames[0].timestamp_utc
                self._chunk_starts.append(len(self._elapsed))
                self._chunks.append(chunk)
                self._elapsed.extend(max(0.0, (frame.timestamp_utc - origin).total_seconds())
                                     for frame in frames)
        if not self._elapsed:
            raise DataSourceError("recording contains no frames")
        self._state = DataSourceState.DISCONNECTED
        self._index = 0
        self._playback_speed = 1.0
        self._lock = RLock()
        self.playback_speed = playback_speed

    @property
    def mode(self) -> DataMode:
        return DataMode.SIMULATION if self._metadata.simulated else DataMode.DEVICE

    @property
    def state(self) -> DataSourceState:
        with self._lock:
            return self._state

    @property
    def frame_rate_hz(self) -> float:
        return self._metadata.frame_rate_hz

    @property
    def playback_speed(self) -> float:
        with self._lock:
            return self._playback_speed

    @playback_speed.setter
    def playback_speed(self, value: float) -> None:
        speed = float(value)
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("playback_speed must be positive and finite")
        with self._lock:
            self._playback_speed = speed

    @property
    def duration_seconds(self) -> float:
        return self._elapsed[-1]

    @property
    def position_seconds(self) -> float:
        with self._lock:
            if self._index >= len(self._elapsed):
                return self.duration_seconds
            return self._elapsed[self._index]

    @property
    def frame_count(self) -> int:
        return len(self._elapsed)

    def discover(self) -> tuple[DeviceDescriptor, ...]:
        return (
            DeviceDescriptor(
                id=self._device_id,
                name=f"Recorded study {self.study_id}",
                simulated=self._metadata.simulated,
            ),
        )

    def connect(self, device_id: str | None = None) -> None:
        if device_id not in (None, self._device_id):
            raise DataSourceError(f"unknown recording source: {device_id}")
        with self._lock:
            if self._state is DataSourceState.RUNNING:
                raise DataSourceError("cannot connect while playback is running")
            self._state = DataSourceState.CONNECTED

    def disconnect(self) -> None:
        with self._lock:
            self._state = DataSourceState.DISCONNECTED

    def configure(self, settings: AcquisitionSettings) -> None:
        with self._lock:
            if self._state not in {DataSourceState.CONNECTED, DataSourceState.CONFIGURED}:
                raise DataSourceError("connect the recording before configuring it")
            if not math.isclose(
                settings.sample_rate_hz, self.frame_rate_hz, rel_tol=0.0, abs_tol=1e-9
            ):
                raise DataSourceError(
                    "recording sample rate does not match study settings"
                )
            self._state = DataSourceState.CONFIGURED

    def start(self) -> None:
        with self._lock:
            if self._state is not DataSourceState.CONFIGURED:
                raise DataSourceError("configure the recording before starting playback")
            self._state = DataSourceState.RUNNING

    def stop(self) -> None:
        with self._lock:
            if self._state is not DataSourceState.RUNNING:
                raise DataSourceError("recording playback is not running")
            self._state = DataSourceState.CONFIGURED

    def reconnect(self) -> None:
        with self._lock:
            was_configured = self._state in {
                DataSourceState.CONFIGURED, DataSourceState.RUNNING
            }
        self.disconnect()
        self.connect()
        if was_configured:
            self.configure(AcquisitionSettings(sample_rate_hz=self.frame_rate_hz))

    def read_frame(self) -> SourceFrame:
        with self._lock:
            if self._state is not DataSourceState.RUNNING:
                raise DataSourceError("start playback before reading frames")
            if self._index >= len(self._elapsed):
                self._state = DataSourceState.CONFIGURED
                raise RecordingPlaybackComplete("recording playback is complete")
            chunk = bisect_right(self._chunk_starts, self._index) - 1
            if chunk != self._loaded_chunk:
                from ..storage.recording import RecordingError

                try:
                    self._chunk_frames = self._chunks[chunk].read()
                except (OSError, RecordingError) as exc:
                    raise DataSourceError(f"cannot read recording chunk: {exc}") from exc
                self._loaded_chunk = chunk
            frame = self._chunk_frames[self._index - self._chunk_starts[chunk]]
            self._index += 1
            return frame

    def seek(self, seconds: float) -> float:
        """Move to the first frame at or after an offset from recording start."""
        value = float(seconds)
        if not math.isfinite(value):
            raise ValueError("seek position must be finite")
        with self._lock:
            if self._state is DataSourceState.RUNNING:
                raise DataSourceError("pause playback before seeking")
            clamped = min(max(0.0, value), self.duration_seconds)
            self._index = bisect_left(self._elapsed, clamped)
            if self._index >= len(self._elapsed):
                self._index = len(self._elapsed) - 1
            return self._elapsed[self._index]

    @property
    def _device_id(self) -> str:
        return f"recording:{self.study_id}:{self.session_id}"
