import time
import unittest
from datetime import datetime, timedelta, timezone

from app.application import AcquisitionPipeline
from app.config import DataMode
from app.data_sources import DataSource, DataSourceError, DataSourceState, DeviceDescriptor
from app.domain import AcquisitionSettings, DataQuality, EITFrame


NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def make_frame(sequence):
    value = float(sequence + 1)
    return EITFrame(
        sequence_number=sequence,
        timestamp_utc=NOW + timedelta(milliseconds=40 * sequence),
        belt_index=0,
        global_impedance=value,
        roi_impedance=(value,) * 8,
        reconstructed_delta_z=((value,),),
        quality=DataQuality.VALID,
        simulated=True,
    )


class BurstSource(DataSource):
    def __init__(self, sequences):
        self._sequences = iter(sequences)
        self._state = DataSourceState.RUNNING

    @property
    def mode(self):
        return DataMode.SIMULATION

    @property
    def state(self):
        return self._state

    def discover(self):
        return (DeviceDescriptor("burst", "Burst", True),)

    def connect(self, device_id=None):
        self._state = DataSourceState.CONNECTED

    def disconnect(self):
        self._state = DataSourceState.DISCONNECTED

    def configure(self, settings: AcquisitionSettings):
        self._state = DataSourceState.CONFIGURED

    def start(self):
        self._state = DataSourceState.RUNNING

    def stop(self):
        self._state = DataSourceState.CONFIGURED

    def reconnect(self):
        self._state = DataSourceState.CONNECTED

    def read_frame(self):
        try:
            return make_frame(next(self._sequences))
        except StopIteration as exc:
            raise DataSourceError("end of burst") from exc


class AcquisitionPipelineTest(unittest.TestCase):
    def test_bounded_ring_buffer_reports_overflow_gap_latency_and_load(self):
        source = BurstSource([0, 1, 4, *range(5, 22)])
        pipeline = AcquisitionPipeline(source, capacity=5, clock=lambda: NOW + timedelta(seconds=2))
        pipeline.start()
        snapshot = pipeline.wait_for_received(20, 1.0)
        pipeline.stop()

        self.assertEqual([item.sequence_number for item in snapshot.frames], [17, 18, 19, 20, 21])
        self.assertEqual(snapshot.metrics.received_frames, 20)
        self.assertEqual(snapshot.metrics.dropped_frames, 2)
        self.assertEqual(snapshot.metrics.buffer_overflows, 15)
        self.assertEqual(snapshot.metrics.queue_depth, 5)
        self.assertEqual(snapshot.metrics.queue_capacity, 5)
        self.assertEqual(snapshot.metrics.last_sequence_number, 21)
        self.assertGreaterEqual(snapshot.metrics.maximum_latency_ms, 0.0)

    def test_out_of_order_frame_is_rejected_and_counted(self):
        pipeline = AcquisitionPipeline(BurstSource([0, 1, 1]), capacity=5, clock=lambda: NOW)
        pipeline.start()
        pipeline.wait_for_received(2, 1.0)
        deadline = time.monotonic() + 1.0
        while pipeline.last_error is None and time.monotonic() < deadline:
            time.sleep(0.001)
        snapshot = pipeline.snapshot()
        pipeline.stop()

        self.assertEqual(snapshot.metrics.out_of_order_frames, 1)
        self.assertIsNotNone(pipeline.last_error)

    def test_snapshot_is_immutable_and_does_not_block_caller(self):
        pipeline = AcquisitionPipeline(BurstSource(range(100)), capacity=10, clock=lambda: NOW)
        started = time.monotonic()
        pipeline.start()
        snapshot = pipeline.wait_for_received(10, 1.0)
        elapsed = time.monotonic() - started
        pipeline.stop()

        self.assertIsInstance(snapshot.frames, tuple)
        self.assertLess(elapsed, 0.5)
        with self.assertRaises(Exception):
            snapshot.metrics.received_frames = 0


if __name__ == "__main__":
    unittest.main()
