import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.application import (
    ElectrodeContactStatus, ElectrodeQualityBlockedError, EventType,
)
from app.config import AppConfig, DataMode
from app.container import ApplicationContainer
from app.domain import CalibrationStatus, Patient


class SignalQualityTest(unittest.TestCase):
    def make_container(self, directory: str) -> ApplicationContainer:
        root = Path(directory)
        return ApplicationContainer.build(AppConfig(
            data_mode=DataMode.SIMULATION,
            database_path=root / "db.sqlite3",
            raw_data_dir=root / "frames",
            export_dir=root / "exports",
            log_path=root / "logs.jsonl",
            simulation_duration_seconds=30.0,
        ))

    def prepare_study(self, container: ApplicationContainer):
        patient = Patient(external_id="QUALITY-1")
        container.repositories.patients.save(patient)
        lifecycle = container.study_lifecycle
        lifecycle.select_patient(patient.id)
        study = lifecycle.create_study()
        lifecycle.prepare()
        return study

    def test_calibration_is_saved_in_study_and_restored_from_database(self):
        with TemporaryDirectory() as directory:
            container = self.make_container(directory)
            try:
                study = self.prepare_study(container)
                container.data_source.electrode_contact_levels = lambda: (0.9,) * 16

                result = container.electrode_quality.calibrate()

                self.assertEqual(result.status, CalibrationStatus.SUCCEEDED)
                restored = container.repositories.studies.get(study.id)
                self.assertEqual(restored.calibration, result)
                self.assertEqual(restored.calibration.usable_measurement_ratio, 1.0)
            finally:
                container.shutdown()

    def test_test_electrode_loss_changes_channel_emits_event_and_blocks_start(self):
        with TemporaryDirectory() as directory:
            container = self.make_container(directory)
            try:
                self.prepare_study(container)
                events = []
                container.event_bus.subscribe(
                    EventType.ELECTRODE_QUALITY_CHANGED, events.append
                )
                levels = [0.9] * 16
                container.data_source.electrode_contact_levels = lambda: tuple(levels)
                container.electrode_quality.refresh()
                levels[6] = 0.0

                snapshot = container.electrode_quality.refresh()

                self.assertEqual(
                    snapshot.contacts[6].status,
                    ElectrodeContactStatus.TECHNICAL_ERROR,
                )
                self.assertEqual(events[-1].payload["electrodes"], (7,))
                self.assertFalse(snapshot.start_allowed)
                with self.assertRaises(ElectrodeQualityBlockedError):
                    container.study_lifecycle.start()
                self.assertIsNone(container.study_lifecycle.current_session)
                result = container.electrode_quality.calibrate()
                self.assertEqual(result.status, CalibrationStatus.FAILED)
                self.assertEqual(result.failed_electrodes, (7,))
                self.assertIn("technical_error", result.reason)
            finally:
                container.shutdown()

    def test_simulator_electrode_loss_is_reported_for_electrode_seven(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            container = ApplicationContainer.build(AppConfig(
                data_mode=DataMode.SIMULATION,
                simulation_scenario="electrode_loss",
                simulation_duration_seconds=0.4,
                database_path=root / "db.sqlite3",
                raw_data_dir=root / "frames",
                export_dir=root / "exports",
                log_path=root / "logs.jsonl",
            ))
            try:
                self.prepare_study(container)
                container.monitoring_controller.start()
                deadline = time.monotonic() + 1.0
                while (
                    container.monitoring.acquisition_metrics.received_frames < 6
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                snapshot = container.electrode_quality.refresh()
                self.assertEqual(
                    snapshot.contacts[6].status,
                    ElectrodeContactStatus.TECHNICAL_ERROR,
                )
                self.assertTrue(all(
                    item.status is ElectrodeContactStatus.STRONG
                    for index, item in enumerate(snapshot.contacts)
                    if index != 6
                ))
            finally:
                container.shutdown()

    def test_fromfile_start_does_not_require_live_electrode_diagnostics(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            container = ApplicationContainer.build(AppConfig(
                data_mode=DataMode.FROMFILE,
                fromfile_path=Path("examples/fromfile/eupnea.json"),
                database_path=root / "db.sqlite3",
                raw_data_dir=root / "frames",
                export_dir=root / "exports",
                log_path=root / "logs.jsonl",
            ))
            try:
                self.prepare_study(container)

                container.monitoring_controller.start()

                self.assertEqual(container.study_lifecycle.status.value, "running")
                self.assertIsNotNone(container.study_lifecycle.current_session)
                self.assertTrue(container.monitoring_controller.is_running)
            finally:
                container.shutdown()


if __name__ == "__main__":
    unittest.main()
