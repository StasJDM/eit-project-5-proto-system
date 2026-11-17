from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4
from types import SimpleNamespace
import numpy as np

import app.application  # Load application package before storage (shared type graph).
from app.application import EventBus, MonitoringSnapshot, TrendService
from app.application.monitoring import TrendSample
from app.application.monitoring import _trend
from app.screens.trends_screen import (
    _format_elapsed, _median_reduce, _relative_percent, _trend_median_factor,
    _upward_bar_geometry,
)
from app.config import DataMode
from app.domain import (
    AcquisitionSettings, DataQuality, MonitoringSession, Patient, Study,
    StudyStatus, TrendAggregate,
)
from app.storage import Database, RepositoryBundle


class TrendStorageTest(unittest.TestCase):
    def test_positive_and_negative_columns_both_grow_upward(self):
        positive = _upward_bar_geometry(5.0, 10.0, 100.0, 80.0)
        negative = _upward_bar_geometry(-5.0, 10.0, 100.0, 80.0)

        self.assertEqual(positive, negative)
        self.assertEqual(positive, (60.0, 40.0))

    def test_presentation_helpers_use_real_ranges_and_robust_level_change(self):
        values = _relative_percent(np.asarray([2.0, 3.0, np.nan, 4.0]))
        np.testing.assert_allclose(values[[0, 1, 3]], [0.0, 50.0, 100.0])
        self.assertTrue(np.isnan(values[2]))
        self.assertEqual(_format_elapsed(300), "5:00м")
        self.assertEqual(_format_elapsed(3600), "1:00ч")
        self.assertEqual(_trend_median_factor("manual_adult", 1800), 3)
        self.assertEqual(_trend_median_factor("manual_adult", 21600), 9)
        self.assertEqual(_trend_median_factor("manual_adult", 86400), 27)
        self.assertEqual(_trend_median_factor("manual_infant", 900), 3)
        self.assertEqual(_trend_median_factor("manual_infant", 86400), 243)
        np.testing.assert_allclose(
            _median_reduce(np.asarray([1.0, 5.0, 3.0, 8.0]), 3),
            [3.0, 8.0],
        )

        breath = np.sin(np.linspace(0.0, 20.0 * np.pi, 1500))
        shifted = breath + np.linspace(0.0, 0.2, breath.size)
        self.assertGreater(_trend(shifted), 0.0)

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
                    metric_values=(("tvi_au", 1.0 + index),),
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
            self.assertEqual(loaded[0].metric_value("tvi_au"), 2.0)
            by_position = RepositoryBundle.build(reopened).trends.list_position_range(
                study.id, 20.0, 50.0
            )
            self.assertEqual([point.position_seconds for point in by_position], [29.0, 44.0])
            self.assertEqual(
                RepositoryBundle.build(reopened).trends.position_bounds(study.id),
                (14.0, 44.0),
            )
            self.assertEqual(
                RepositoryBundle.build(reopened).trends.first_usable(study.id).global_value,
                0.0,
            )
            reopened.close()

    def test_aggregate_uses_active_session_time_and_analysis_quality(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        study = Study(
            patient_id=uuid4(), settings=AcquisitionSettings(),
            status=StudyStatus.RUNNING, simulated=True,
            created_at_utc=now, updated_at_utc=now,
        )
        session = MonitoringSession(
            study_id=study.id,
            started_at_utc=now,
            accumulated_pause_seconds=30.0,
            simulated=True,
        )

        class Repository:
            def __init__(self):
                self.points = []

            def append(self, point):
                self.points.append(point)

        class Monitoring:
            def __init__(self):
                self.handler = None
                self.snapshot = MonitoringSnapshot(
                    rr=None, quality=DataQuality.UNAVAILABLE,
                    quality_reason="no_detectable_breathing",
                )

            def subscribe_trend_samples(self, handler):
                self.handler = handler
                return lambda: None

        repository = Repository()
        monitoring = Monitoring()
        lifecycle = SimpleNamespace(
            status=StudyStatus.RUNNING,
            current_study=study,
            current_session=session,
        )
        service = TrendService(repository, monitoring, lifecycle, EventBus())
        monitoring.handler(TrendSample(
            sequence_number=1,
            timestamp_utc=now + timedelta(seconds=45),
            global_value=1.0,
            roi_values=(0.1,) * 8,
            quality=DataQuality.UNAVAILABLE,
            quality_reason="no_detectable_breathing",
            metric_values=(
                ("eeli_au", 0.4), ("eili_au", 1.4), ("tvi_au", 1.0),
                ("mvi_au_per_min", 15.0), ("rr_bpm", 15.0),
                ("right_left_ratio", 1.1), ("ventral_dorsal_ratio", 0.9),
                ("right_percent", 52.0), ("left_percent", 48.0),
                *((f"roi_{index}_tvi_au", 0.125) for index in range(1, 9)),
                *((f"roi_{index}_percent", 12.5) for index in range(1, 9)),
            ),
        ))
        service.flush()

        self.assertEqual(len(repository.points), 1)
        self.assertEqual(repository.points[0].position_seconds, 15.0)
        self.assertEqual(repository.points[0].quality, DataQuality.UNAVAILABLE)
        self.assertEqual(
            repository.points[0].quality_reason, "no_detectable_breathing"
        )
        point = repository.points[0]
        for code in (
            "eeli_au", "eili_au", "tvi_au", "mli_au", "mvi_au_per_min",
            "rr_bpm", "right_left_ratio", "ventral_dorsal_ratio",
            "right_percent", "left_percent",
            *(f"roi_{index}_tvi_au" for index in range(1, 9)),
            *(f"roi_{index}_percent" for index in range(1, 9)),
        ):
            with self.subTest(metric=code):
                self.assertIsNotNone(point.metric_value(code))
        self.assertEqual(point.metric_value("mli_au"), 1.0)

    def test_archived_frame_uses_current_session_position_at_receipt(self):
        started = datetime(2026, 1, 2, tzinfo=timezone.utc)
        archived = started - timedelta(days=10)
        study = Study(
            patient_id=uuid4(), settings=AcquisitionSettings(),
            status=StudyStatus.RUNNING, simulated=True,
            created_at_utc=started, updated_at_utc=started,
        )
        session = MonitoringSession(
            study_id=study.id, started_at_utc=started, simulated=True
        )

        class Repository:
            def __init__(self):
                self.points = []

            def append(self, point):
                self.points.append(point)

        class Monitoring:
            def subscribe_trend_samples(self, handler):
                self.handler = handler
                return lambda: None

        repository = Repository()
        monitoring = Monitoring()
        lifecycle = SimpleNamespace(
            status=StudyStatus.RUNNING,
            current_study=study,
            current_session=session,
        )
        service = TrendService(
            repository, monitoring, lifecycle, EventBus(),
            clock=lambda: started + timedelta(seconds=42),
        )
        monitoring.handler(TrendSample(
            sequence_number=1,
            timestamp_utc=archived,
            global_value=1.0,
            roi_values=(0.1,) * 8,
            quality=DataQuality.VALID,
        ))
        monitoring.handler(TrendSample(
            sequence_number=376,
            timestamp_utc=archived + timedelta(seconds=15),
            global_value=2.0,
            roi_values=(0.2,) * 8,
            quality=DataQuality.VALID,
        ))
        service.flush()

        self.assertEqual(
            [point.position_seconds for point in repository.points], [42.0, 57.0]
        )

    def test_collapsed_legacy_positions_are_read_on_relative_timeline(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "simulation.sqlite3"
            now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            db = Database(path, DataMode.SIMULATION)
            repositories = RepositoryBundle.build(db)
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
            repositories.patients.save(patient)
            repositories.studies.save(study)
            repositories.sessions.save(session)
            repository = repositories.trends
            study_id = study.id
            session_id = session.id
            for index in range(4):
                end = now + timedelta(seconds=index * 15)
                repository.append(TrendAggregate(
                    study_id=study_id,
                    session_id=session_id,
                    interval_start_utc=end - timedelta(seconds=14),
                    interval_end_utc=end,
                    position_seconds=0.0,
                    aggregation_kind="interval",
                    sample_count=1,
                    global_value=float(index),
                    right_value=None,
                    left_value=None,
                    roi_values=(None,) * 8,
                    respiratory_rate_bpm=None,
                    quality=DataQuality.VALID,
                    algorithm_version="legacy",
                    simulated=True,
                ))

            self.assertEqual(repository.position_bounds(study_id), (14.0, 59.0))
            points = repository.list_position_range(study_id, 10.0, 35.0)
            self.assertEqual(
                [point.position_seconds for point in points], [14.0, 29.0]
            )
            self.assertEqual(repository.first_usable(study_id).position_seconds, 14.0)
            db.close()


if __name__ == "__main__":
    unittest.main()
