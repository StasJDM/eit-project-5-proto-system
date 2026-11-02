from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import app.application  # Load application package before storage (shared type graph).
from app.config import DataMode
from app.domain import (
    AcquisitionSettings, DataQuality, MonitoringSession, Patient, Study,
    StudyStatus, TrendAggregate,
)
from app.storage import Database, RepositoryBundle


class TrendStorageTest(unittest.TestCase):
    def test_persisted_aggregates_are_range_queryable_after_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "simulation.sqlite3"
            now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            patient = Patient()
            study = Study(
                patient_id=patient.id,
                settings=AcquisitionSettings(),
                status=StudyStatus.RUNNING,
                simulated=True,
                created_at_utc=now,
                updated_at_utc=now,
            )
            session = MonitoringSession(
                study_id=study.id, started_at_utc=now, simulated=True
            )
            db = Database(path, DataMode.SIMULATION)
            repos = RepositoryBundle.build(db)
            repos.patients.save(patient)
            repos.studies.save(study)
            repos.sessions.save(session)
            for index in range(3):
                start = now + timedelta(seconds=index * 15)
                repos.trends.append(TrendAggregate(
                    study_id=study.id,
                    session_id=session.id,
                    interval_start_utc=start,
                    interval_end_utc=start + timedelta(seconds=14),
                    position_seconds=float(index * 15 + 14),
                    aggregation_kind="interval",
                    sample_count=375,
                    global_value=float(index),
                    right_value=40.0 + index,
                    left_value=60.0 - index,
                    roi_values=tuple(float(index + roi) for roi in range(8)),
                    respiratory_rate_bpm=15.0,
                    quality=DataQuality.VALID,
                    algorithm_version="test-1",
                    simulated=True,
                ))
            db.close()

            reopened = Database(path, DataMode.SIMULATION)
            loaded = RepositoryBundle.build(reopened).trends.list_range(
                study.id, now + timedelta(seconds=15), now + timedelta(seconds=31)
            )
            self.assertEqual([point.global_value for point in loaded], [1.0, 2.0])
            self.assertEqual(loaded[0].algorithm_version, "test-1")
            self.assertEqual(loaded[0].sample_count, 375)
            reopened.close()


if __name__ == "__main__":
    unittest.main()
