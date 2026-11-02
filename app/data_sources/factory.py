"""Construction of the configured EIT data source."""

from __future__ import annotations

from ..config import AppConfig, DataMode
from .base import DataSource
from .device import DeviceDataSource
from .json_file import JSONMeasurementDataSource
from .simulation import SimulationDataSource


class DataSourceUnavailableError(RuntimeError):
    """Raised when the selected source has no installed adapter."""


def create_data_source(config: AppConfig) -> DataSource:
    if config.data_mode is DataMode.SIMULATION:
        return SimulationDataSource(
            seed=config.simulation_seed,
            scenario=config.simulation_scenario,
            playback_speed=config.simulation_speed,
            respiratory_rate_bpm=config.simulation_respiratory_rate_bpm,
            duration_seconds=config.simulation_duration_seconds,
        )
    if config.data_mode is DataMode.FROMFILE:
        return JSONMeasurementDataSource(
            config.fromfile_path,
            playback_speed=config.fromfile_speed,
            simulated=True,
            restart_on_connect=True,
            loop_playback=True,
        )
    return DeviceDataSource(config.device_endpoint)

