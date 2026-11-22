from collections import Counter
import zipfile
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from uuid import uuid4

from app.config import AppConfig, DataMode
from app.container import ApplicationContainer
from app.data_sources import RawMeasurementFrame
from app.domain import DataQuality, EITFrame, Patient
from app.storage import (
    AcquisitionRecordingStore,
    InsufficientDiskSpaceError,
    RecordingError,
)


NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def raw_frame(sequence, *, simulated=False):
    return RawMeasurementFrame(
        sequence_number=sequence,
        timestamp_utc=NOW + timedelta(milliseconds=40 * sequence),
        channel_values=tuple(float(sequence + channel) for channel in range(208)),
        simulated=simulated,
    )


def eit_frame(sequence):
    value = float(sequence + 1)
    return EITFrame(
        sequence_number=sequence,
        timestamp_utc=NOW + timedelta(milliseconds=40 * sequence),
        belt_index=0,
        global_impedance=value,
        roi_impedance=(value,) * 8,
        reconstructed_delta_z=((value, value), (value, value)),
        quality=DataQuality.VALID,
        simulated=True,
    )


class AcquisitionRecordingTest(unittest.TestCase):
    def test_raw_frames_are_batched_checksummed_and_round_trip_exactly(self):
        with TemporaryDirectory() as directory:
            store = AcquisitionRecordingStore(
                directory, simulated=False, chunk_size=2, minimum_free_bytes=0
            )
            study_id, session_id = uuid4(), uuid4()
            expected = tuple(raw_frame(index) for index in range(5))
            writer = store.open_writer(study_id, session_id, frame_rate_hz=25.0)
            for item in expected:
                writer.append(item)
            writer.close()

            manifest_path = Path(directory) / str(study_id) / str(session_id) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["frame_count"], 5)
            self.assertEqual([item["frame_count"] for item in manifest["chunks"]], [2, 2, 1])
            self.assertTrue(all(len(item["sha256"]) == 64 for item in manifest["chunks"]))
            self.assertEqual(store.load(study_id, session_id), expected)

            first_chunk = manifest_path.parent / manifest["chunks"][0]["file"]
            first_chunk.write_bytes(first_chunk.read_bytes() + b"corruption")
            with self.assertRaisesRegex(RecordingError, "checksum mismatch"):
                store.load(study_id, session_id)

    def test_simulated_eit_frames_use_the_same_recording_path(self):
        with TemporaryDirectory() as directory:
            store = AcquisitionRecordingStore(
                directory, simulated=True, chunk_size=3, minimum_free_bytes=0
            )
            study_id, session_id = uuid4(), uuid4()
            expected = tuple(eit_frame(index) for index in range(4))
            writer = store.open_writer(study_id, session_id, frame_rate_hz=25.0)
            for item in expected:
                writer.append(item)
            writer.close()
            self.assertEqual(store.load(study_id, session_id), expected)

    def test_recorded_block_extracts_each_required_array_once(self):
        with TemporaryDirectory() as directory:
            store = AcquisitionRecordingStore(directory, simulated=True)
            ids = uuid4(), uuid4()
            writer = store.open_writer(*ids, frame_rate_hz=25)
            expected = tuple(eit_frame(index) for index in range(64))
            for frame in expected:
                writer.append(frame)
            writer.close()
            opened = Counter()
            original = zipfile.ZipFile.open

            def observe(archive, name, *args, **kwargs):
                opened[name] += 1
                return original(archive, name, *args, **kwargs)

            with patch.object(zipfile.ZipFile, "open", observe):
                self.assertEqual(store.load(*ids), expected)
            self.assertEqual(len(opened), 10)
            self.assertEqual(set(opened.values()), {1})

    def test_recovery_preserves_confirmed_chunks_after_interruption(self):
        with TemporaryDirectory() as directory:
            store = AcquisitionRecordingStore(
                directory, simulated=False, chunk_size=2, minimum_free_bytes=0
            )
            study_id, session_id = uuid4(), uuid4()
            writer = store.open_writer(study_id, session_id, frame_rate_hz=25.0)
            writer.append(raw_frame(0))
            writer.append(raw_frame(1))
            writer.append(raw_frame(2))  # remains unconfirmed in memory

            recovered = store.recover_incomplete()
            self.assertEqual(len(recovered), 1)
            manifest = json.loads(recovered[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "interrupted")
            self.assertEqual(manifest["frame_count"], 2)
            self.assertEqual(store.load(study_id, session_id), (raw_frame(0), raw_frame(1)))

    def test_free_space_and_checksum_are_enforced(self):
        with TemporaryDirectory() as directory:
            store = AcquisitionRecordingStore(
                directory, simulated=False, chunk_size=1, minimum_free_bytes=1024
            )
            writer = store.open_writer(uuid4(), uuid4(), frame_rate_hz=25.0)
            with patch(
                "app.storage.recording.shutil.disk_usage",
                return_value=Mock(free=0),
            ):
                with self.assertRaises(InsufficientDiskSpaceError):
                    writer.append(raw_frame(0))

    def test_monitoring_controller_starts_source_and_recording_as_one_session(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig(
                data_mode=DataMode.SIMULATION,
                database_path=root / "db.sqlite3",
                raw_data_dir=root / "frames",
                export_dir=root / "exports",
                log_path=root / "logs.jsonl",
            )
            container = ApplicationContainer.build(config)
            try:
                patient = Patient(external_id="REC-1")
                container.repositories.patients.save(patient)
                lifecycle = container.study_lifecycle
                lifecycle.select_patient(patient.id)
                study = lifecycle.create_study()
                lifecycle.prepare()
                before = container.monitoring.acquisition_metrics.received_frames
                container.monitoring_controller.start()
                deadline = time.monotonic() + 1.0
                while (
                    container.monitoring.acquisition_metrics.received_frames < before + 3
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                session_id = lifecycle.current_session.id
                container.monitoring_controller.stop()

                frames = container.recording_store.load(study.id, session_id)
                self.assertGreaterEqual(len(frames), 1)
                self.assertTrue(all(item.simulated for item in frames))
            finally:
                container.shutdown()


if __name__ == "__main__":
    unittest.main()
