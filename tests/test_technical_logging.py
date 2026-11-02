import json
import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.config import AppConfig, DataMode
from app.container import ApplicationContainer
from app.technical_logging import (
    configure_logging,
    get_logger,
    log_context,
    technical_event,
)


def close_managed_handlers() -> None:
    logger = logging.getLogger("eit")
    for handler in tuple(logger.handlers):
        if getattr(handler, "_eit_managed", False):
            logger.removeHandler(handler)
            handler.close()


class TechnicalLoggingTest(unittest.TestCase):
    def tearDown(self) -> None:
        close_managed_handlers()

    def test_json_log_has_correlation_and_does_not_emit_free_text_or_pii_fields(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "eit.jsonl"
            configure_logging(AppConfig(log_path=path))
            logger = get_logger("test")
            study_id = uuid4()
            session_id = uuid4()

            with log_context(study_id=study_id, session_id=session_id):
                technical_event(
                    logger,
                    logging.INFO,
                    "session.started",
                    session_state="running",
                    simulated=True,
                )
                logger.warning("Patient Ivan Ivanov, diagnosis secret")

            with self.assertRaisesRegex(ValueError, "unsafe technical log fields"):
                technical_event(
                    logger,
                    logging.INFO,
                    "unsafe.event",
                    patient_name="Ivan Ivanov",
                )

            close_managed_handlers()
            records = [json.loads(line) for line in path.read_text().splitlines()]
            first = records[0]
            self.assertEqual(first["event"], "session.started")
            self.assertEqual(first["study_id"], str(study_id))
            self.assertEqual(first["session_id"], str(session_id))
            self.assertEqual(first["correlation_id"], str(session_id))
            self.assertEqual(records[1]["event"], "unstructured_log_ignored")
            self.assertNotIn("Ivan", path.read_text())
            self.assertNotIn("diagnosis", path.read_text())

    def test_rotation_bounds_log_file_count(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "eit.jsonl"
            configure_logging(
                AppConfig(
                    log_path=path,
                    log_max_bytes=350,
                    log_backup_count=2,
                )
            )
            logger = get_logger("rotation")
            for sequence in range(100):
                technical_event(
                    logger,
                    logging.INFO,
                    "frame.received",
                    sequence_number=sequence,
                    quality="valid",
                    simulated=True,
                )
            close_managed_handlers()

            files = sorted(path.parent.glob("eit.jsonl*"))
            self.assertLessEqual(len(files), 3)
            self.assertGreater(len(files), 1)
            for file_path in files:
                for line in file_path.read_text().splitlines():
                    json.loads(line)

    def test_device_source_is_not_started_before_a_monitoring_session(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "device.jsonl"
            config = AppConfig(
                data_mode=DataMode.DEVICE,
                database_path=Path(":memory:"),
                raw_data_dir=root / "frames",
                export_dir=root / "exports",
                log_path=log_path,
            )
            configure_logging(config)

            container = ApplicationContainer.build(config)
            container.shutdown()
            close_managed_handlers()

            records = [json.loads(line) for line in log_path.read_text().splitlines()]
            events = {record["event"] for record in records}
            self.assertIn("application.starting", events)
            self.assertNotIn("data_source.start_failed", events)
            self.assertNotIn("endpoint", log_path.read_text().lower())


if __name__ == "__main__":
    unittest.main()
