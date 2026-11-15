import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.config import DataMode
from app.domain import (
    AcquisitionSettings,
    DataQuality,
    EITFrame,
    Event,
    EventCategory,
    MonitoringSession,
    Patient,
    Report,
    ReportStatus,
    Study,
    StudyStatus,
)
from app.storage import (
    LATEST_SCHEMA_VERSION,
    Database,
    DatabaseModeError,
    NpzFrameStore,
    RepositoryBundle,
)


NOW = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)


def make_frame(sequence: int) -> EITFrame:
    value = float(sequence + 1)
    return EITFrame(
        sequence_number=sequence,
        timestamp_utc=NOW + timedelta(milliseconds=40 * sequence),
        belt_index=0,
        global_impedance=value,
        roi_impedance=(value,) * 8,
        reconstructed_delta_z=((0.0, 1.0), (1.0, 0.0)),
        absolute_conductivity=((0.5, 1.0), (1.5, 2.0)),
        quality=DataQuality.VALID,
        simulated=True,
    )


class StorageTest(unittest.TestCase):
    def test_clean_database_crud_persists_after_reopen(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "simulation.sqlite3"
            database = Database(path, DataMode.SIMULATION)
            repositories = RepositoryBundle.build(database)
            patient = Patient(
                external_id="P-001",
                created_at_utc=NOW,
                updated_at_utc=NOW,
            )
            study = Study(
                patient_id=patient.id,
                settings=AcquisitionSettings(),
                simulated=True,
                created_at_utc=NOW,
                updated_at_utc=NOW,
            )
            session = MonitoringSession(
                study_id=study.id,
                started_at_utc=NOW,
                simulated=True,
            )
            event = Event(
                study_id=study.id,
                session_id=session.id,
                occurred_at_utc=NOW,
                category=EventCategory.MARKER,
                text="marker",
                created_at_utc=NOW,
                simulated=True,
            )
            report = Report(
                study_id=study.id,
                period_start_utc=NOW,
                period_end_utc=NOW + timedelta(minutes=1),
                status=ReportStatus.DRAFT,
                template_version="v1",
                algorithm_versions=("metrics-v1",),
                created_at_utc=NOW,
                simulated=True,
            )

            repositories.patients.save(patient)
            repositories.studies.save(study)
            repositories.sessions.save(session)
            repositories.events.append(study.id, event)
            repositories.reports.save(report)
            repositories.settings.save({"language": "ru", "scale": 2})
            database.close()

            reopened = Database(path, DataMode.SIMULATION)
            loaded = RepositoryBundle.build(reopened)
            try:
                self.assertEqual(loaded.patients.get(patient.id), patient)
                self.assertEqual(loaded.studies.get(study.id), study)
                self.assertEqual(loaded.sessions.get(session.id), session)
                self.assertEqual(loaded.events.list_for_study(study.id), (event,))
                self.assertEqual(loaded.events.list_all(), (event,))
                self.assertEqual(loaded.reports.get(report.id), report)
                self.assertEqual(loaded.settings.load(), {"language": "ru", "scale": 2})
                self.assertEqual(reopened.schema_version, LATEST_SCHEMA_VERSION)
                self.assertEqual(
                    reopened.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1
                )

                updated_patient = replace(patient, family_name="Петров")
                updated_study = replace(study, status=StudyStatus.READY)
                updated_report = replace(report, status=ReportStatus.GENERATED)
                loaded.patients.save(updated_patient)
                loaded.studies.save(updated_study)
                loaded.reports.save(updated_report)
                loaded.settings.save({"language": "en"})
                self.assertEqual(loaded.patients.get(patient.id), updated_patient)
                self.assertEqual(loaded.studies.get(study.id), updated_study)
                self.assertEqual(loaded.reports.get(report.id), updated_report)
                self.assertEqual(
                    loaded.settings.load(), {"language": "en", "scale": 2}
                )

                loaded.studies.delete(study.id)
                self.assertIsNone(loaded.studies.get(study.id))
                self.assertIsNone(loaded.sessions.get(session.id))
                self.assertEqual(loaded.events.list_for_study(study.id), ())
                self.assertIsNone(loaded.reports.get(report.id))
                loaded.patients.delete(patient.id)
                self.assertIsNone(loaded.patients.get(patient.id))
            finally:
                reopened.close()

    def test_previous_schema_is_migrated_without_losing_records(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "migration.sqlite3"
            old = Database(path, DataMode.SIMULATION, target_version=1)
            patient = Patient(created_at_utc=NOW, updated_at_utc=NOW)
            study = Study(
                patient_id=patient.id,
                settings=AcquisitionSettings(),
                simulated=True,
                created_at_utc=NOW,
                updated_at_utc=NOW,
            )
            old_repositories = RepositoryBundle.build(old)
            old_repositories.patients.save(patient)
            old_repositories.studies.save(study)
            old.close()

            migrated = Database(path, DataMode.SIMULATION)
            repositories = RepositoryBundle.build(migrated)
            try:
                self.assertEqual(migrated.schema_version, LATEST_SCHEMA_VERSION)
                self.assertEqual(repositories.patients.get(patient.id), patient)
                session = MonitoringSession(
                    study_id=study.id,
                    started_at_utc=NOW,
                    simulated=True,
                )
                repositories.sessions.save(session)
                self.assertEqual(repositories.sessions.get(session.id), session)
            finally:
                migrated.close()

    def test_transactions_constraints_and_mode_separation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "simulation.sqlite3"
            database = Database(path, DataMode.SIMULATION)
            repositories = RepositoryBundle.build(database)
            first = Patient(external_id="duplicate")
            second = Patient(external_id="duplicate")
            repositories.patients.save(first)
            with self.assertRaises(sqlite3.IntegrityError):
                repositories.patients.save(second)
            self.assertEqual(repositories.patients.list(), (first,))
            with self.assertRaises(DatabaseModeError):
                repositories.studies.save(
                    Study(
                        patient_id=first.id,
                        settings=AcquisitionSettings(),
                        simulated=False,
                    )
                )
            database.close()

            with self.assertRaises(DatabaseModeError):
                Database(path, DataMode.DEVICE)

    def test_compressed_frame_chunks_round_trip_separately_from_sqlite(self):
        with TemporaryDirectory() as directory:
            store = NpzFrameStore(Path(directory) / "frames", simulated=True)
            study_id = uuid4()
            session_id = uuid4()
            frames = (make_frame(0), make_frame(1))

            chunk_path = store.append_chunk(study_id, session_id, frames)

            self.assertEqual(chunk_path.suffix, ".npz")
            self.assertEqual(store.load(study_id, session_id), frames)
            with self.assertRaises(FileExistsError):
                store.append_chunk(study_id, session_id, frames)
