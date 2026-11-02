import unittest
from datetime import datetime, timedelta, timezone
from queue import Empty, Queue

from app.data_sources import (
    PROTOCOL_NAME,
    PROTOCOL_VERSION,
    DataSourceEventType,
    DataSourceError,
    DataSourceState,
    DataSourceTimeoutError,
    DataSourceTimingPolicy,
    DeviceDataSource,
    DeviceProtocolError,
    TimestampSource,
)
from app.domain import AcquisitionSettings


NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def ack(command, *, version=PROTOCOL_VERSION):
    payload = {"type": "ack", "command": command, "protocol_version": version}
    if command == "hello":
        payload["protocol"] = PROTOCOL_NAME
    return payload


def frame(sequence, *, electrode_quality=None):
    payload = {
        "type": "frame",
        "protocol_version": PROTOCOL_VERSION,
        "sequence_number": sequence,
        "timestamp_utc": (NOW + timedelta(milliseconds=40 * sequence)).isoformat(),
        "channels": [float(sequence + 1)] * 208,
        "quality": "valid",
    }
    if electrode_quality is not None:
        payload["electrode_quality"] = electrode_quality
    return payload


class FakeTransport:
    def __init__(self, messages):
        self.messages = Queue()
        for message in messages:
            self.messages.put(message)
        self.sent = []
        self.closed = False

    def send(self, payload):
        if self.closed:
            raise DataSourceError("transport closed")
        self.sent.append(payload)

    def receive(self, timeout_seconds):
        try:
            value = self.messages.get(timeout=timeout_seconds)
        except Empty as exc:
            raise DataSourceTimeoutError("test timeout") from exc
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.closed = True


class DeviceDataSourceTest(unittest.TestCase):
    def make_source(self, messages, *, queue_capacity=32):
        transport = FakeTransport(messages)
        policy = DataSourceTimingPolicy(
            connect_timeout_seconds=0.1,
            read_timeout_seconds=0.02,
            stale_after_seconds=0.04,
            max_consecutive_timeouts=100,
            reconnect_backoff_seconds=(0.01,),
        )
        source = DeviceDataSource(
            "tcp://device.test:9000",
            transport_factory=lambda _endpoint, _timeout: transport,
            timing_policy=policy,
            queue_capacity=queue_capacity,
            clock=lambda: NOW,
        )
        return source, transport

    def test_handshake_configuration_threaded_stream_and_safe_stop(self):
        messages = [ack("hello"), ack("configure"), ack("start")]
        messages.extend(frame(index) for index in range(1000))
        source, transport = self.make_source(messages, queue_capacity=16)

        source.connect()
        source.configure(AcquisitionSettings())
        source.start()
        received = tuple(source.read_frame() for _ in range(1000))
        source.stop()
        source.disconnect()

        self.assertEqual([item.sequence_number for item in received], list(range(1000)))
        self.assertTrue(all(item.timestamp_source is TimestampSource.DEVICE for item in received))
        self.assertTrue(all(not item.simulated for item in received))
        self.assertEqual(source.state, DataSourceState.DISCONNECTED)
        self.assertTrue(transport.closed)
        self.assertEqual([item["type"] for item in transport.sent[:3]], ["hello", "configure", "start"])
        self.assertEqual(transport.sent[-1]["type"], "stop")

    def test_protocol_version_is_verified_before_configuration(self):
        source, _transport = self.make_source([ack("hello", version=2)])
        with self.assertRaises(DeviceProtocolError):
            source.connect()

    def test_gap_and_corrupt_frame_become_events_and_errors(self):
        messages = [ack("hello"), ack("configure"), ack("start"), frame(0), frame(2)]
        messages.append({"type": "frame", "protocol_version": 1, "sequence_number": 3})
        source, _transport = self.make_source(messages)
        source.connect()
        source.configure(AcquisitionSettings())
        source.start()
        self.assertEqual(source.read_frame().sequence_number, 0)
        self.assertEqual(source.read_frame().sequence_number, 2)
        with self.assertRaises(DeviceProtocolError):
            source.read_frame()
        events = source.drain_events()
        self.assertTrue(any(item.type is DataSourceEventType.FRAME_GAP for item in events))
        self.assertTrue(any(item.type is DataSourceEventType.ERROR for item in events))
        self.assertEqual(source.state, DataSourceState.FAILED)
        source.stop()
        source.disconnect()

    def test_reconnect_recreates_transport_and_restores_configuration(self):
        first = FakeTransport([ack("hello"), ack("configure")])
        second = FakeTransport([ack("hello"), ack("configure")])
        transports = iter((first, second))
        source = DeviceDataSource(
            "tcp://device.test:9000",
            transport_factory=lambda _endpoint, _timeout: next(transports),
            clock=lambda: NOW,
        )
        source.connect()
        source.configure(AcquisitionSettings())

        source.reconnect()

        self.assertTrue(first.closed)
        self.assertEqual(source.state, DataSourceState.CONFIGURED)
        self.assertEqual([item["type"] for item in second.sent], ["hello", "configure"])
        source.disconnect()

    def test_device_frame_updates_electrode_contact_diagnostics(self):
        levels = [0.9] * 16
        levels[6] = 0.0
        source, _transport = self.make_source([
            ack("hello"), ack("configure"), ack("start"),
            frame(0, electrode_quality=levels),
        ])
        source.connect()
        source.configure(AcquisitionSettings())
        source.start()
        source.read_frame()
        self.assertEqual(source.electrode_contact_levels()[6], 0.0)
        source.stop()
        source.disconnect()


if __name__ == "__main__":
    unittest.main()
