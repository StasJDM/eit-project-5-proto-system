import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.application import (
    EventBus, EventType, MonitoringMode, MonitoringService, StudyPlaybackService,
)
from app.data_sources import (
    DataSourceError, DataSourceState, RecordingPlaybackComplete,
    RecordingPlaybackDataSource, SimulationDataSource,
)
from app.domain import (
    AcquisitionSettings, DataQuality, EITFrame, MonitoringSession, Study, StudyStatus,
)
from app.storage import AcquisitionRecordingStore


NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def frame(sequence: int) -> EITFrame:
    value = float(sequence + 1)
    return EITFrame(
        sequence_number=sequence,
        timestamp_utc=NOW + timedelta(milliseconds=40 * sequence),
        belt_index=0,
        global_impedance=value,
        roi_impedance=tuple(value + index for index in range(8)),
        reconstructed_delta_z=((value, value), (value, value)),
        absolute_conductivity=((0.8, 1.2), (1.1, 0.9)),
        quality=DataQuality.VALID,
        simulated=True,
    )


def make_recording(root: str, count: int = 8):
    store = AcquisitionRecordingStore(
        root, simulated=True, chunk_size=3, minimum_free_bytes=0
    )
    study_id, session_id = uuid4(), uuid4()
    writer = store.open_writer(study_id, session_id, frame_rate_hz=25.0)
    expected = tuple(frame(index) for index in range(count))
    for item in expected:
        writer.append(item)
    writer.close()
    return store, study_id, session_id, expected


def digest_tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class _LifecycleStub:
    def __init__(self, study: Study, session: MonitoringSession) -> None:
        self.study = study
        self.current_session = session

    def open_study(self, study_id):
        if study_id != self.study.id:
            raise RuntimeError("unknown study")
        return self.study


class RecordingPlaybackTest(unittest.TestCase):
    def test_file_source_replays_exact_frames_and_seeks_by_recorded_time(self):
        with TemporaryDirectory() as directory:
            store, study_id, session_id, expected = make_recording(directory)
            before = digest_tree(Path(directory))
            source = RecordingPlaybackDataSource(store, study_id, session_id)

            source.connect()
            source.configure(AcquisitionSettings())
            source.start()
            self.assertEqual(tuple(source.read_frame() for _ in range(3)), expected[:3])
            source.stop()
            self.assertAlmostEqual(source.seek(0.081), 0.12)
            source.playback_speed = 4.0
            source.start()
            self.assertEqual(source.read_frame(), expected[3])
            for _ in expected[4:]:
                source.read_frame()
            with self.assertRaises(RecordingPlaybackComplete):
                source.read_frame()

            self.assertEqual(source.state, DataSourceState.CONFIGURED)
            self.assertEqual(digest_tree(Path(directory)), before)

    def test_invalid_speed_and_non_completed_recording_are_rejected(self):
        with TemporaryDirectory() as directory:
            store = AcquisitionRecordingStore(
                directory, simulated=True, chunk_size=1, minimum_free_bytes=0
            )
            study_id, session_id = uuid4(), uuid4()
            writer = store.open_writer(study_id, session_id, frame_rate_hz=25.0)
            writer.append(frame(0))
            writer.close(completed=False)
            with self.assertRaises(DataSourceError):
                RecordingPlaybackDataSource(store, study_id, session_id)

            store2, study_id2, session_id2, _ = make_recording(
                str(Path(directory) / "other")
            )
            with self.assertRaises(ValueError):
                RecordingPlaybackDataSource(
                    store2, study_id2, session_id2, playback_speed=0
                )

    def test_service_marks_playback_read_only_and_restores_live_source(self):
        with TemporaryDirectory() as directory:
            store, study_id, session_id, _ = make_recording(directory, count=30)
            settings = AcquisitionSettings()
            study = Study(
                id=study_id,
                patient_id=uuid4(),
                settings=settings,
                status=StudyStatus.COMPLETED,
                simulated=True,
            )
            session = MonitoringSession(
                id=session_id,
                study_id=study_id,
                started_at_utc=NOW,
                ended_at_utc=NOW + timedelta(seconds=1.2),
                simulated=True,
            )
            lifecycle = _LifecycleStub(study, session)
            live = SimulationDataSource(duration_seconds=10.0)
            bus = EventBus()
            events = []
            bus.subscribe(EventType.PLAYBACK_CHANGED, events.append)
            monitoring = MonitoringService(live, bus)
            service = StudyPlaybackService(
                store,
                monitoring,
                lifecycle,
                bus,
                live_source=live,
                live_settings_provider=lambda: settings,
            )
            try:
                service.open(study_id, session_id, speed=0.5)
                self.assertTrue(service.snapshot.active)
                self.assertTrue(service.snapshot.read_only)
                self.assertEqual(monitoring.mode, MonitoringMode.PLAYBACK)
                service.pause()
                self.assertAlmostEqual(service.seek(0.4), 0.4)
                service.set_speed(2.0)
                self.assertEqual(service.snapshot.speed, 2.0)
                service.close()
                self.assertFalse(service.snapshot.active)
                self.assertEqual(monitoring.mode, MonitoringMode.LIVE)
                self.assertIs(monitoring.source, live)
                self.assertTrue(events[0].payload["read_only"])
                self.assertFalse(events[-1].payload["read_only"])
            finally:
                monitoring.stop()


if __name__ == "__main__":
    unittest.main()
