"""Read-only playback source for external 208-channel EIT recordings."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
import math
from pathlib import Path

from ..config import DataMode
from ..domain import AcquisitionSettings, utc_now
from .base import (
    DataSource, DataSourceError, DataSourceState, DeviceDescriptor,
    TimestampSource,
)
from .json_contract import (
    JSONMeasurementRecording,
    RawMeasurementFrame,
    load_json_measurement_recording,
)
from .tabular_contract import load_tabular_measurement_recording


class JSONPlaybackComplete(DataSourceError):
    """The external JSON recording has reached its final frame."""


class JSONMeasurementDataSource(DataSource):
    """Expose a validated external JSON file through the normal data pipeline."""

    is_playback = True
    study_id = None
    session_id = None

    def __init__(
        self,
        path: str | Path,
        *,
        fallback_frame_rate_hz: float = 25.0,
        playback_speed: float = 1.0,
        simulated: bool = False,
        restart_on_connect: bool = False,
        loop_playback: bool = False,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        loader = (
            load_json_measurement_recording
            if self.path.suffix.lower() == ".json"
            else load_tabular_measurement_recording
        )
        self.recording: JSONMeasurementRecording = loader(
            self.path,
            fallback_frame_rate_hz=fallback_frame_rate_hz,
            simulated=simulated,
        )
        self._frames = self.recording.frames
        self._elapsed = tuple(
            max(
                0.0,
                (frame.timestamp_utc - self._frames[0].timestamp_utc).total_seconds(),
            )
            for frame in self._frames
        )
        self._state = DataSourceState.DISCONNECTED
        self._index = 0
        self._restart_on_connect = restart_on_connect
        self._loop_playback = loop_playback
        self._clock = clock
        self._stream_started_at_utc: datetime | None = None
        self._playback_speed = 1.0
        self.playback_speed = playback_speed

    @property
    def mode(self) -> DataMode:
        return DataMode.FROMFILE

    @property
    def state(self) -> DataSourceState:
        return self._state

    @property
    def frame_rate_hz(self) -> float:
        return self.recording.frame_rate_hz

    @property
    def playback_speed(self) -> float:
        return self._playback_speed

    @playback_speed.setter
    def playback_speed(self, value: float) -> None:
        speed = float(value)
        if not math.isfinite(speed) or speed <= 0:
            raise ValueError("playback_speed must be positive and finite")
        self._playback_speed = speed

    @property
    def duration_seconds(self) -> float:
        return self._elapsed[-1]

    @property
    def position_seconds(self) -> float:
        if self._loop_playback:
            return self._index / self.frame_rate_hz
        if self._index >= len(self._frames):
            return self.duration_seconds
        return self._elapsed[self._index]

    @property
    def suggested_settings(self) -> AcquisitionSettings:
        return AcquisitionSettings(
            injection_current_ma=self.recording.excitation_current_ma or 5.0,
            injection_frequency_khz=self.recording.excitation_frequency_khz or 100.0,
            electrode_count=16,
            belt_count=1,
            sample_rate_hz=self.frame_rate_hz,
        )

    @property
    def reconstruction_reference_frames(self) -> tuple[RawMeasurementFrame, ...]:
        count = min(
            len(self._frames), max(3, round(self.frame_rate_hz))
        )
        frames = self._frames[:count]
        if len(frames) >= 3:
            return frames
        # Static phantom files from the measurement generator may contain only
        # one or two snapshots. Repeating them gives the robust reference
        # estimator its minimum sample count without inventing new values.
        return frames + tuple(
            frames[index % len(frames)] for index in range(3 - len(frames))
        )

    def discover(self) -> tuple[DeviceDescriptor, ...]:
        return (
            DeviceDescriptor(
                str(self.path), self.path.name, self.recording.frames[0].simulated
            ),
        )

    def connect(self, device_id: str | None = None) -> None:
        if device_id not in (None, str(self.path)):
            raise DataSourceError(f"unknown measurement file source: {device_id}")
        if self._state is DataSourceState.RUNNING:
            raise DataSourceError("cannot connect while file playback is running")
        if self._restart_on_connect and self._state is DataSourceState.DISCONNECTED:
            self._index = 0
            self._stream_started_at_utc = None
        self._state = DataSourceState.CONNECTED

    def disconnect(self) -> None:
        self._state = DataSourceState.DISCONNECTED

    def configure(self, settings: AcquisitionSettings) -> None:
        if self._state not in {DataSourceState.CONNECTED, DataSourceState.CONFIGURED}:
            raise DataSourceError("connect the recording before configuring it")
        if settings.electrode_count != 16 or settings.belt_count != 1:
            raise DataSourceError("file reconstruction supports one 16-electrode belt")
        if not math.isclose(
            settings.sample_rate_hz, self.frame_rate_hz, rel_tol=0.0, abs_tol=1e-9
        ):
            raise DataSourceError("recording frame rate does not match acquisition settings")
        self._state = DataSourceState.CONFIGURED

    def start(self) -> None:
        if self._state is not DataSourceState.CONFIGURED:
            raise DataSourceError("configure the recording before playback")
        self._state = DataSourceState.RUNNING
        if self._loop_playback and self._stream_started_at_utc is None:
            self._stream_started_at_utc = self._clock()

    def stop(self) -> None:
        if self._state is DataSourceState.RUNNING:
            self._state = DataSourceState.CONFIGURED

    def reconnect(self) -> None:
        was_configured = self._state in {
            DataSourceState.CONFIGURED, DataSourceState.RUNNING
        }
        self.disconnect()
        self.connect()
        if was_configured:
            self.configure(self.suggested_settings)

    def read_frame(self) -> RawMeasurementFrame:
        if self._state is not DataSourceState.RUNNING:
            raise DataSourceError("JSON recording is not running")
        if self._index >= len(self._frames) and not self._loop_playback:
            self._state = DataSourceState.CONFIGURED
            raise JSONPlaybackComplete("JSON measurement playback is complete")
        stream_index = self._index
        frame_index = stream_index % len(self._frames)
        frame = self._frames[frame_index]
        if self._loop_playback:
            assert self._stream_started_at_utc is not None
            frame = replace(
                frame,
                sequence_number=self._frames[0].sequence_number + stream_index,
                timestamp_utc=self._stream_started_at_utc + timedelta(
                    seconds=stream_index / self.frame_rate_hz
                ),
                timestamp_source=TimestampSource.SYNTHESIZED,
            )
        self._index += 1
        return frame

    def seek(self, seconds: float) -> float:
        value = float(seconds)
        if not math.isfinite(value):
            raise ValueError("seek position must be finite")
        if self._state is DataSourceState.RUNNING:
            raise DataSourceError("pause JSON playback before seeking")
        clamped = min(max(0.0, value), self.duration_seconds)
        self._index = min(bisect_left(self._elapsed, clamped), len(self._frames) - 1)
        return self._elapsed[self._index]
