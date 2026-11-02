"""Reproducible simulated implementation of the EIT data-source contract."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import Enum
import math

import numpy as np

from ..config import DataMode
from ..domain import AcquisitionSettings, DataQuality, EITFrame, ReconstructionMap
from ..mock_data import BreathingSimulator
from .base import (
    DataSource, DataSourceError, DataSourceEvent, DataSourceEventType,
    DataSourceState, DeviceDescriptor,
)


SIMULATED_DEVICE_ID = "eit-simulator"
_MAP_SIZE = 64


class SimulationScenario(str, Enum):
    EUPNEA = "eupnea"
    APNEA = "apnea"
    TACHYPNEA = "tachypnea"
    ELECTRODE_LOSS = "electrode_loss"
    NOISE = "noise"
    DISCONNECT = "disconnect"


class SimulationScenarioComplete(DataSourceError):
    """The configured finite simulation scenario reached its duration."""


class SimulationDataSource(DataSource):
    def __init__(
        self,
        *,
        seed: int = 0,
        scenario: str | SimulationScenario = SimulationScenario.EUPNEA,
        playback_speed: float = 1.0,
        respiratory_rate_bpm: float = 12.0,
        duration_seconds: float = 300.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        try:
            self._scenario = SimulationScenario(scenario)
        except ValueError as exc:
            raise ValueError(f"unknown simulation scenario: {scenario!r}") from exc
        if not math.isfinite(playback_speed) or playback_speed <= 0:
            raise ValueError("playback_speed must be positive and finite")
        if not math.isfinite(respiratory_rate_bpm) or not 5.0 <= respiratory_rate_bpm <= 30.0:
            raise ValueError("respiratory_rate_bpm must be between 5 and 30")
        if not math.isfinite(duration_seconds) or duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive and finite")
        self._seed = seed
        self._playback_speed = float(playback_speed)
        self._respiratory_rate_bpm = float(respiratory_rate_bpm)
        self._duration_seconds = float(duration_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._state = DataSourceState.DISCONNECTED
        self._settings: AcquisitionSettings | None = None
        self._simulator: BreathingSimulator | None = None
        self._sequence_number = 0
        self._events: list[DataSourceEvent] = []
        self._started_at_utc: datetime | None = None
        self._scenario_rng = np.random.default_rng(seed + 10_000)

    @property
    def scenario(self) -> SimulationScenario:
        return self._scenario

    @property
    def playback_speed(self) -> float:
        return self._playback_speed

    @property
    def duration_seconds(self) -> float:
        return self._duration_seconds

    @property
    def respiratory_rate_bpm(self) -> float:
        return self._respiratory_rate_bpm

    @property
    def mode(self) -> DataMode:
        return DataMode.SIMULATION

    @property
    def state(self) -> DataSourceState:
        return self._state

    def drain_events(self) -> tuple[DataSourceEvent, ...]:
        events = tuple(self._events)
        self._events.clear()
        return events

    def electrode_contact_levels(self) -> tuple[float | None, ...]:
        levels = [0.92 - (index % 4) * 0.025 for index in range(16)]
        if self._scenario is SimulationScenario.NOISE:
            levels = [0.56 - (index % 3) * 0.03 for index in range(16)]
        maximum_frames = max(
            1,
            round(
                self._duration_seconds
                * (self._settings.sample_rate_hz if self._settings else 25.0)
            ),
        )
        if (
            self._scenario is SimulationScenario.ELECTRODE_LOSS
            and self._sequence_number >= max(1, maximum_frames // 2)
        ):
            levels[6] = 0.0  # deterministic test loss: electrode №7
        if self._scenario is SimulationScenario.DISCONNECT and self._state is DataSourceState.FAILED:
            return (None,) * 16
        return tuple(levels)

    def discover(self) -> tuple[DeviceDescriptor, ...]:
        return (
            DeviceDescriptor(
                id=SIMULATED_DEVICE_ID,
                name="EIT breathing simulator",
                simulated=True,
            ),
        )

    def connect(self, device_id: str | None = None) -> None:
        if device_id not in (None, SIMULATED_DEVICE_ID):
            raise self._error(f"Unknown simulated device: {device_id}")
        if self._state is DataSourceState.RUNNING:
            raise self._error("Cannot connect while the source is running")
        self._set_state(DataSourceState.CONNECTED)

    def disconnect(self) -> None:
        if self._state is DataSourceState.RUNNING:
            self.stop()
        self._settings = None
        self._simulator = None
        self._set_state(DataSourceState.DISCONNECTED)

    def configure(self, settings: AcquisitionSettings) -> None:
        if self._state not in (DataSourceState.CONNECTED, DataSourceState.CONFIGURED):
            raise self._error("Connect the source before configuring it")
        if settings.belt_count != 1:
            raise self._error("MVP supports one active electrode belt")
        if settings.electrode_count != 16:
            raise self._error("MVP supports 16 electrodes per belt")
        if settings.sample_rate_hz != 25.0:
            raise self._error("The MVP simulator supports a 25 Hz sample rate")
        self._settings = settings
        self._simulator = BreathingSimulator(
            fs=int(settings.sample_rate_hz),
            rr=(
                40.0
                if self._scenario is SimulationScenario.TACHYPNEA
                else self._respiratory_rate_bpm
            ),
            seed=self._seed,
        )
        self._scenario_rng = np.random.default_rng(self._seed + 10_000)
        self._sequence_number = 0
        self._started_at_utc = None
        self._set_state(DataSourceState.CONFIGURED)

    def start(self) -> None:
        if self._state is not DataSourceState.CONFIGURED:
            raise self._error("Configure the source before starting it")
        self._started_at_utc = self._now()
        self._set_state(DataSourceState.RUNNING)

    def stop(self) -> None:
        if self._state is not DataSourceState.RUNNING:
            raise self._error("The source is not running")
        self._set_state(DataSourceState.CONFIGURED)

    def reconnect(self) -> None:
        settings = self._settings
        self.disconnect()
        self.connect()
        if settings is not None:
            self.configure(settings)

    def read_frame(self) -> EITFrame:
        if self._state is not DataSourceState.RUNNING or self._simulator is None:
            raise self._error("Start the source before reading frames")
        if self._settings is None or self._started_at_utc is None:
            raise self._error("Simulation source has no active configuration")

        maximum_frames = max(1, round(
            self._duration_seconds * self._settings.sample_rate_hz
        ))
        if self._sequence_number >= maximum_frames:
            self._set_state(DataSourceState.CONFIGURED)
            raise SimulationScenarioComplete("Simulation scenario is complete")
        if (
            self._scenario is SimulationScenario.DISCONNECT
            and self._sequence_number >= max(1, maximum_frames // 2)
        ):
            self._set_state(DataSourceState.FAILED)
            raise self._error("Simulated device connection was lost", recoverable=True)

        self._simulator.step()
        waveforms = self._simulator.get_waveforms(
            window_sec=1.0 / self._simulator.fs
        )
        global_value = float(waveforms["global"][-1])
        roi_values = tuple(float(values[-1]) for values in waveforms["rois"])
        quality = DataQuality.VALID
        progress = self._sequence_number / maximum_frames
        if self._scenario is SimulationScenario.APNEA:
            global_value = max(0.0, 0.02 + float(self._scenario_rng.normal(0.0, 0.0005)))
            roi_values = tuple(
                max(0.0, 0.02 + float(self._scenario_rng.normal(0.0, 0.0005)))
                for _ in range(8)
            )
        elif self._scenario is SimulationScenario.NOISE:
            global_value += float(self._scenario_rng.normal(0.0, 0.35))
            roi_values = tuple(
                value + float(self._scenario_rng.normal(0.0, 0.35))
                for value in roi_values
            )
            quality = DataQuality.DEGRADED
        elif self._scenario is SimulationScenario.ELECTRODE_LOSS and progress >= 0.5:
            roi_values = (0.0, *roi_values[1:])
            quality = DataQuality.DEGRADED

        timestamp_utc = self._started_at_utc + timedelta(
            seconds=self._sequence_number / self._settings.sample_rate_hz
        )

        frame = EITFrame(
            sequence_number=self._sequence_number,
            timestamp_utc=timestamp_utc,
            belt_index=0,
            global_impedance=global_value,
            roi_impedance=roi_values,
            reconstructed_delta_z=_reconstruct_mock_map(roi_values),
            quality=quality,
            simulated=True,
        )
        self._sequence_number += 1
        return frame

    def _set_state(self, state: DataSourceState) -> None:
        self._state = state
        occurred_at = self._clock()
        if occurred_at.tzinfo is None:
            raise DataSourceError("Simulation clock must return a timezone-aware value")
        self._events.append(DataSourceEvent(
            type=DataSourceEventType.STATE_CHANGED,
            occurred_at_utc=occurred_at.astimezone(timezone.utc),
            state=state,
        ))

    def _error(self, message: str, *, recoverable: bool = True) -> DataSourceError:
        occurred_at = self._clock()
        if occurred_at.tzinfo is not None:
            self._events.append(DataSourceEvent(
                type=DataSourceEventType.ERROR,
                occurred_at_utc=occurred_at.astimezone(timezone.utc),
                state=self._state,
                message=message,
                recoverable=recoverable,
            ))
        return DataSourceError(message)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None:
            raise DataSourceError("Simulation clock must return a timezone-aware value")
        return value.astimezone(timezone.utc)


def _reconstruct_mock_map(roi_values: tuple[float, ...]) -> ReconstructionMap:
    """Build a deterministic 2-D mock map from eight synchronized ROI values."""

    y, x = np.mgrid[-1.0:1.0:complex(_MAP_SIZE), -1.0:1.0:complex(_MAP_SIZE)]
    thorax = (x / 0.92) ** 2 + (y / 0.82) ** 2 <= 1.0
    right_lung = ((x + 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0
    left_lung = ((x - 0.34) / 0.34) ** 2 + (y / 0.62) ** 2 <= 1.0
    result = np.zeros((_MAP_SIZE, _MAP_SIZE), dtype=float)

    row_edges = np.linspace(-0.82, 0.82, 5)
    for region in range(4):
        upper_bound = (
            y <= row_edges[region + 1]
            if region == 3
            else y < row_edges[region + 1]
        )
        band = (y >= row_edges[region]) & upper_bound
        result[right_lung & band] = roi_values[region]
        result[left_lung & band] = roi_values[region + 4]

    result[~thorax] = 0.0
    return tuple(tuple(float(value) for value in row) for row in result)

