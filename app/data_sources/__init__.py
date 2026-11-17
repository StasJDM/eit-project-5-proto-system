"""Data-source contracts and adapters."""

from .base import (
    DataSource,
    DataSourceError,
    DataSourceEvent,
    DataSourceEventType,
    DataSourceSequenceError,
    DataSourceState,
    DataSourceTimeoutError,
    DataSourceTimingPolicy,
    DeviceDescriptor,
    FrameSequenceTracker,
    TimestampSource,
)
from .json_contract import (
    JSONMeasurementFormatError,
    JSONMeasurementRecording,
    RawMeasurementFrame,
    load_json_measurement_recording,
    parse_json_measurement_recording,
)
from .device import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    DeviceDataSource,
    DeviceProtocolError,
    DeviceTransport,
    JsonLineSocketTransport,
)
from .recording import RecordingPlaybackComplete, RecordingPlaybackDataSource
from .json_file import JSONMeasurementDataSource, JSONPlaybackComplete
from .tabular_contract import (
    TabularMeasurementFormatError,
    load_tabular_measurement_recording,
)
from .factory import DataSourceUnavailableError, create_data_source
from .simulation import (
    SimulationDataSource,
    SimulationScenario,
    SimulationScenarioComplete,
)

__all__ = [
    "DataSource",
    "DataSourceError",
    "DataSourceEvent",
    "DataSourceEventType",
    "DataSourceSequenceError",
    "DataSourceState",
    "DataSourceTimeoutError",
    "DataSourceTimingPolicy",
    "DataSourceUnavailableError",
    "DeviceDataSource",
    "DeviceProtocolError",
    "DeviceTransport",
    "DeviceDescriptor",
    "FrameSequenceTracker",
    "JSONMeasurementFormatError",
    "JSONMeasurementDataSource",
    "JSONMeasurementRecording",
    "JSONPlaybackComplete",
    "TabularMeasurementFormatError",
    "JsonLineSocketTransport",
    "PROTOCOL_NAME",
    "PROTOCOL_VERSION",
    "RawMeasurementFrame",
    "RecordingPlaybackComplete",
    "RecordingPlaybackDataSource",
    "SimulationDataSource",
    "SimulationScenario",
    "SimulationScenarioComplete",
    "TimestampSource",
    "create_data_source",
    "load_json_measurement_recording",
    "load_tabular_measurement_recording",
    "parse_json_measurement_recording",
]

