import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import AppConfig, DataMode
from app.container import ApplicationContainer
from app.data_sources import (
    DeviceDataSource,
    JSONMeasurementDataSource,
    SimulationDataSource,
    create_data_source,
)


class AppConfigTest(unittest.TestCase):
    def test_bundled_recording_is_the_default(self):
        config = AppConfig.from_env({})

        self.assertEqual(config.data_mode, DataMode.FROMFILE)
        self.assertEqual(
            config.fromfile_path,
            Path("examples/fromfile/2x_circle_r0.15_20260608_211810.json"),
        )
        self.assertEqual(config.database_path, Path("data/fromfile/eit.sqlite3"))
        self.assertEqual(config.raw_data_dir, Path("data/fromfile/frames"))
        self.assertEqual(config.log_path, Path("data/fromfile/logs/eit.jsonl"))
        source = create_data_source(config)
        self.assertIsInstance(source, JSONMeasurementDataSource)
        self.assertEqual(len(source.recording.frames), 1)
        self.assertEqual(len(source.recording.frames[0].channel_values), 208)
        self.assertEqual(len(source.reconstruction_reference_frames), 3)

    def test_default_single_frame_phantom_builds_and_streams(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig.from_env({
                "EIT_FROMFILE_SPEED": "100",
                "EIT_DATABASE_PATH": str(root / "db.sqlite3"),
                "EIT_RAW_DATA_DIR": str(root / "frames"),
                "EIT_EXPORT_DIR": str(root / "exports"),
                "EIT_LOG_PATH": str(root / "eit.jsonl"),
            })
            container = ApplicationContainer.build(config)
            try:
                container.monitoring.start()
                deadline = time.monotonic() + 2.0
                while (
                    container.monitoring.acquisition_metrics.received_frames < 3
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)

                self.assertTrue(container.monitoring.is_running)
                self.assertGreaterEqual(
                    container.monitoring.acquisition_metrics.received_frames, 3
                )
                self.assertEqual(
                    len(container.monitoring.snapshot.reconstruction_map), 64
                )
            finally:
                container.shutdown()

    def test_mode_and_seed_are_read_from_environment(self):
        config = AppConfig.from_env(
            {
                "EIT_DATA_MODE": " SIMULATION ",
                "EIT_SIMULATION_SEED": "42",
                "EIT_SIMULATION_SCENARIO": "tachypnea",
                "EIT_SIMULATION_SPEED": "2.5",
                "EIT_SIMULATION_RR_BPM": "10",
                "EIT_SIMULATION_DURATION_SECONDS": "90",
            }
        )

        self.assertEqual(config.data_mode, DataMode.SIMULATION)
        self.assertEqual(config.simulation_seed, 42)
        self.assertEqual(config.simulation_scenario, "tachypnea")
        self.assertEqual(config.simulation_speed, 2.5)
        self.assertEqual(config.simulation_respiratory_rate_bpm, 10.0)
        self.assertEqual(config.simulation_duration_seconds, 90.0)
        source = create_data_source(config)
        self.assertEqual(source.scenario.value, "tachypnea")
        self.assertEqual(source.playback_speed, 2.5)
        self.assertEqual(source.respiratory_rate_bpm, 10.0)

    def test_invalid_simulation_breathing_rate_uses_calm_default(self):
        config = AppConfig.from_env({"EIT_SIMULATION_RR_BPM": "60"})

        self.assertEqual(config.simulation_respiratory_rate_bpm, 12.0)
        self.assertTrue(any(
            "EIT_SIMULATION_RR_BPM" in item for item in config.diagnostics
        ))

    def test_invalid_mode_falls_back_to_simulation_with_diagnostic(self):
        config = AppConfig.from_env({"EIT_DATA_MODE": "unknown"})

        self.assertEqual(config.data_mode, DataMode.SIMULATION)
        self.assertTrue(any("Unknown EIT_DATA_MODE" in item for item in config.diagnostics))

    def test_device_mode_selects_hardware_source(self):
        config = AppConfig.from_env(
            {"EIT_DATA_MODE": "device", "EIT_DEVICE_ENDPOINT": "tcp://device:9000"}
        )

        source = create_data_source(config)

        self.assertIsInstance(source, DeviceDataSource)
        self.assertEqual(source.mode, DataMode.DEVICE)

    def test_fromfile_mode_selects_bundled_recording_and_marks_it_simulated(self):
        path = Path("examples/fromfile/eupnea.json")
        config = AppConfig.from_env(
            {
                "EIT_DATA_MODE": "fromfile",
                "EIT_FROMFILE_PATH": str(path),
                "EIT_FROMFILE_SPEED": "2.0",
            }
        )

        source = create_data_source(config)

        self.assertEqual(config.data_mode, DataMode.FROMFILE)
        self.assertTrue(config.simulated)
        self.assertIsInstance(source, JSONMeasurementDataSource)
        self.assertEqual(source.mode, DataMode.FROMFILE)
        self.assertEqual(source.playback_speed, 2.0)
        self.assertEqual(len(source.recording.frames), 300)
        self.assertTrue(all(frame.simulated for frame in source.recording.frames))
        source.connect()
        source.configure(source.suggested_settings)
        source.start()
        first = source.read_frame()
        for _ in range(len(source.recording.frames) - 1):
            source.read_frame()
        looped = source.read_frame()
        self.assertEqual(looped.sequence_number, len(source.recording.frames))
        self.assertAlmostEqual(
            (looped.timestamp_utc - first.timestamp_utc).total_seconds(),
            len(source.recording.frames) / source.frame_rate_hz,
        )
        source.stop()
        source.disconnect()
        source.connect()
        source.configure(source.suggested_settings)
        source.start()
        self.assertEqual(source.read_frame().sequence_number, first.sequence_number)
        source.stop()
        source.disconnect()

    def test_fromfile_mode_reports_missing_file(self):
        config = AppConfig.from_env(
            {
                "EIT_DATA_MODE": "fromfile",
                "EIT_FROMFILE_PATH": "/missing/eit.json",
            }
        )

        self.assertTrue(any("EIT_FROMFILE_PATH" in item for item in config.diagnostics))

    def test_fromfile_mode_runs_through_monitoring_pipeline(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig.from_env(
                {
                    "EIT_DATA_MODE": "fromfile",
                    "EIT_FROMFILE_PATH": "examples/fromfile/project6_400khz_6_frames.json",
                    "EIT_FROMFILE_SPEED": "100",
                    "EIT_DATABASE_PATH": str(root / "fromfile.sqlite3"),
                    "EIT_RAW_DATA_DIR": str(root / "frames"),
                    "EIT_EXPORT_DIR": str(root / "exports"),
                }
            )
            container = ApplicationContainer.build(config)
            try:
                container.monitoring.start()
                deadline = time.monotonic() + 2.0
                while (
                    container.monitoring.acquisition_metrics.received_frames < 305
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                self.assertGreaterEqual(
                    container.monitoring.acquisition_metrics.received_frames, 305
                )
                self.assertTrue(container.monitoring.is_running)
                self.assertGreaterEqual(
                    container.monitoring.acquisition_metrics.last_sequence_number,
                    304,
                )
                self.assertEqual(
                    len(container.monitoring.snapshot.reconstruction_map), 64
                )
                self.assertTrue(all(
                    frame.simulated for frame in container.monitoring.acquisition_frames
                ))
            finally:
                container.shutdown()

    def test_paths_device_parameters_and_log_level_are_configurable(self):
        config = AppConfig.from_env(
            {
                "EIT_DATABASE_PATH": "/tmp/eit.sqlite3",
                "EIT_RAW_DATA_DIR": "/tmp/eit-frames",
                "EIT_EXPORT_DIR": "/tmp/eit-export",
                "EIT_BREATH_MODEL_PATH": "/tmp/breathclf.joblib",
                "EIT_DEVICE_ENDPOINT": "serial:///dev/ttyUSB0",
                "EIT_LOG_LEVEL": "debug",
                "EIT_LOG_PATH": "/tmp/eit-log.jsonl",
                "EIT_LOG_MAX_BYTES": "4096",
                "EIT_LOG_BACKUP_COUNT": "3",
            }
        )

        self.assertEqual(config.database_path, Path("/tmp/eit.sqlite3"))
        self.assertEqual(config.raw_data_dir, Path("/tmp/eit-frames"))
        self.assertEqual(config.export_dir, Path("/tmp/eit-export"))
        self.assertEqual(config.breath_model_path, Path("/tmp/breathclf.joblib"))
        self.assertEqual(config.device_endpoint, "serial:///dev/ttyUSB0")
        self.assertEqual(config.log_level, "DEBUG")
        self.assertEqual(config.log_path, Path("/tmp/eit-log.jsonl"))
        self.assertEqual(config.log_max_bytes, 4096)
        self.assertEqual(config.log_backup_count, 3)

    def test_device_mode_without_driver_does_not_crash_application_startup(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig.from_env(
                {
                    "EIT_DATA_MODE": "device",
                    "EIT_DATABASE_PATH": str(root / "device.sqlite3"),
                    "EIT_RAW_DATA_DIR": str(root / "frames"),
                    "EIT_EXPORT_DIR": str(root / "exports"),
                }
            )
            container = ApplicationContainer.build(config)
            try:
                self.assertFalse(container.monitoring.is_running)
                self.assertTrue(container.startup_diagnostics)
            finally:
                container.shutdown()


if __name__ == "__main__":
    unittest.main()
