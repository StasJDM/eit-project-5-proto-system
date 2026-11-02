import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("EIT_DATABASE_PATH", ":memory:")
os.environ.setdefault("EIT_RAW_DATA_DIR", "/tmp/eit-test-frames")
os.environ.setdefault("EIT_EXPORT_DIR", "/tmp/eit-test-exports")

from PySide6.QtWidgets import QApplication

from app.application import ApplicationEvent, EventBus, EventType, MonitoringService
from app.config import AppConfig, DataMode
from app.container import ApplicationContainer
from app.data_sources import DataSource, DataSourceState, DeviceDescriptor
from app.domain import AcquisitionSettings, DataQuality, EITFrame
from app.main_window import MainWindow


class FakeDataSource(DataSource):
    def __init__(self) -> None:
        self._state = DataSourceState.DISCONNECTED
        self.sequence = 0

    @property
    def mode(self) -> DataMode:
        return DataMode.SIMULATION

    @property
    def state(self) -> DataSourceState:
        return self._state

    def discover(self) -> tuple[DeviceDescriptor, ...]:
        return (DeviceDescriptor("fake", "Fake source", True),)

    def connect(self, device_id: str | None = None) -> None:
        self._state = DataSourceState.CONNECTED

    def disconnect(self) -> None:
        self._state = DataSourceState.DISCONNECTED

    def configure(self, settings: AcquisitionSettings) -> None:
        self._state = DataSourceState.CONFIGURED

    def start(self) -> None:
        self._state = DataSourceState.RUNNING

    def stop(self) -> None:
        self._state = DataSourceState.CONFIGURED

    def reconnect(self) -> None:
        self.disconnect()
        self.connect()

    def read_frame(self) -> EITFrame:
        value = float(self.sequence + 1)
        frame = EITFrame(
            sequence_number=self.sequence,
            timestamp_utc=datetime.now(timezone.utc),
            belt_index=0,
            global_impedance=value,
            roi_impedance=tuple(value + index for index in range(8)),
            reconstructed_delta_z=((value, value), (value, value)),
            quality=DataQuality.VALID,
            simulated=True,
        )
        self.sequence += 1
        return frame


class ApplicationArchitectureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_container(self) -> ApplicationContainer:
        source = FakeDataSource()
        bus = EventBus()
        monitoring = MonitoringService(source, bus)
        monitoring.start()
        monitoring.advance()
        return ApplicationContainer(AppConfig(), bus, source, monitoring)

    def test_monitoring_service_uses_data_source_contract_and_publishes_events(self):
        source = FakeDataSource()
        bus = EventBus()
        received: list[ApplicationEvent] = []
        bus.subscribe(EventType.FRAME_RECEIVED, received.append)
        service = MonitoringService(source, bus)

        service.start()
        frame = service.advance()

        self.assertEqual(frame.sequence_number, 0)
        self.assertEqual(service.get_waveforms()["global"].tolist(), [1.0])
        self.assertEqual(received[0].payload["sequence_number"], 0)
        self.assertEqual(source.state, DataSourceState.RUNNING)

    def test_event_bus_unsubscribe_stops_delivery(self):
        bus = EventBus()
        received: list[ApplicationEvent] = []
        unsubscribe = bus.subscribe(EventType.APPLICATION_ERROR, received.append)
        event = ApplicationEvent(EventType.APPLICATION_ERROR)

        bus.publish(event)
        unsubscribe()
        bus.publish(event)

        self.assertEqual(received, [event])

    def test_main_window_injects_one_read_model_into_all_monitoring_screens(self):
        container = self.make_container()
        window = MainWindow(container)
        try:
            monitoring = container.monitoring
            self.assertIs(window._screens["main"]._monitoring, monitoring)
            self.assertIs(window._screens["analysis"]._monitoring, monitoring)
            self.assertIs(window._screens["trends"]._monitoring, monitoring)
            self.assertFalse(hasattr(window._screens["main"], "_sim"))
            self.assertFalse(hasattr(window._screens["analysis"], "_sim"))
            self.assertFalse(hasattr(window._screens["trends"], "_sim"))
        finally:
            window.close()
            container.shutdown()


if __name__ == "__main__":
    unittest.main()
