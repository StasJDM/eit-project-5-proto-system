import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.application import (
    EventBus,
    InvalidStudyTransition,
    MonitoringController,
    MonitoringControllerError,
    SessionClockService,
    StudyLifecycleService,
)
from app.config import AppConfig, DataMode
from app.container import ApplicationContainer
from app.domain import Patient, StudyStatus
from app.storage import Database, RepositoryBundle


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class DiagnosticSource:
    def electrode_contact_levels(self):
        return (0.9,) * 16


class FakeMonitoring:
    def __init__(self):
        self.source = DiagnosticSource()
        self.is_running = False
        self.start_calls = 0

    def start(self):
        self.start_calls += 1
        self.is_running = True

    def suspend(self):
        self.is_running = False

    def resume(self):
        self.is_running = True

    def stop(self):
        self.is_running = False


class MonitoringControllerTest(unittest.TestCase):
    def test_simulation_keeps_acquiring_after_first_trend_interval(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            container = ApplicationContainer.build(AppConfig(
                data_mode=DataMode.SIMULATION,
                simulation_speed=100.0,
                simulation_duration_seconds=60.0,
                database_path=root / "db.sqlite3",
                raw_data_dir=root / "frames",
                export_dir=root / "exports",
                log_path=root / "logs.jsonl",
            ))
            try:
                patient = Patient(external_id="CTRL-TREND-INTERVAL")
                container.repositories.patients.save(patient)
                lifecycle = container.study_lifecycle
                lifecycle.select_patient(patient.id)
                lifecycle.create_study()
                lifecycle.prepare()
                container.monitoring_controller.start()

                deadline = time.monotonic() + 3.0
                while (
                    container.monitoring.acquisition_metrics.received_frames < 425
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)

                self.assertGreaterEqual(
                    container.monitoring.acquisition_metrics.received_frames, 425
                )
                self.assertTrue(container.monitoring.is_running)
                self.assertIsNone(container.monitoring._pipeline.last_error)
                self.assertIsNotNone(
                    container.trend_service.bounds(lifecycle.current_study.id)
                )
            finally:
                container.shutdown()

    def test_double_start_is_rejected_and_shutdown_finalizes_every_component(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            container = ApplicationContainer.build(AppConfig(
                data_mode=DataMode.SIMULATION,
                database_path=root / "db.sqlite3",
                raw_data_dir=root / "frames",
                export_dir=root / "exports",
                log_path=root / "logs.jsonl",
            ))
            try:
                patient = Patient(external_id="CTRL-1")
                container.repositories.patients.save(patient)
                lifecycle = container.study_lifecycle
                lifecycle.select_patient(patient.id)
                lifecycle.create_study()
                lifecycle.prepare()

                container.monitoring_controller.start()
                with self.assertRaises(InvalidStudyTransition):
                    container.monitoring_controller.start()
                self.assertTrue(container.monitoring.is_running)
                self.assertTrue(container.recording_service.is_recording)

                container.monitoring_controller.shutdown()

                self.assertEqual(lifecycle.status, StudyStatus.COMPLETED)
                self.assertEqual(lifecycle.current_study.conclusion, "application_closed")
                self.assertFalse(container.monitoring.is_running)
                self.assertFalse(container.recording_service.is_recording)
            finally:
                container.shutdown()

    def test_failed_source_start_rolls_back_recording_and_study(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            container = ApplicationContainer.build(AppConfig(
                data_mode=DataMode.SIMULATION,
                database_path=root / "db.sqlite3",
                raw_data_dir=root / "frames",
                export_dir=root / "exports",
                log_path=root / "logs.jsonl",
            ))
            try:
                patient = Patient(external_id="CTRL-ROLLBACK")
                container.repositories.patients.save(patient)
                lifecycle = container.study_lifecycle
                lifecycle.select_patient(patient.id)
                lifecycle.create_study()
                lifecycle.prepare()

                with patch.object(
                    container.monitoring, "start", side_effect=RuntimeError("device failed")
                ):
                    with self.assertRaises(MonitoringControllerError):
                        container.monitoring_controller.start()

                self.assertEqual(lifecycle.status, StudyStatus.FAILED)
                self.assertIsNotNone(lifecycle.current_session.ended_at_utc)
                self.assertFalse(container.monitoring.is_running)
                self.assertFalse(container.recording_service.is_recording)
            finally:
                container.shutdown()

    def test_counters_exclude_pause_and_survive_service_restart(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "clock.sqlite3", DataMode.SIMULATION)
            repositories = RepositoryBundle.build(database)
            clock = Clock()
            bus = EventBus()
            lifecycle = StudyLifecycleService(
                repositories.patients,
                repositories.studies,
                repositories.sessions,
                repositories.settings,
                bus,
                simulated=True,
                clock=clock,
            )
            patient = Patient(external_id="CLOCK-1")
            repositories.patients.save(patient)
            lifecycle.select_patient(patient.id)
            lifecycle.create_study()
            lifecycle.prepare()
            session_clock = SessionClockService(
                lifecycle, repositories.settings, clock=clock
            )
            monitoring = FakeMonitoring()
            controller = MonitoringController(
                lifecycle, monitoring, session_clock, bus
            )
            try:
                self.assertEqual(session_clock.snapshot.eit_seconds, 0.0)
                controller.start()
                clock.advance(5)
                controller.pause()
                paused = session_clock.snapshot
                self.assertEqual(paused.eit_seconds, 5.0)
                self.assertEqual(paused.electrode_system_seconds, 5.0)

                clock.advance(20)
                self.assertEqual(session_clock.snapshot.eit_seconds, 5.0)
                self.assertEqual(session_clock.snapshot.electrode_system_seconds, 5.0)

                controller.resume()
                clock.advance(7)
                controller.stop()
                self.assertEqual(session_clock.snapshot.eit_seconds, 12.0)
                self.assertEqual(session_clock.snapshot.electrode_system_seconds, 12.0)

                restored_lifecycle = StudyLifecycleService(
                    repositories.patients,
                    repositories.studies,
                    repositories.sessions,
                    repositories.settings,
                    EventBus(),
                    simulated=True,
                    clock=clock,
                )
                restored_clock = SessionClockService(
                    restored_lifecycle, repositories.settings, clock=clock
                )
                self.assertEqual(restored_clock.snapshot.eit_seconds, 12.0)
                self.assertEqual(
                    restored_clock.snapshot.electrode_system_seconds, 12.0
                )
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
