import csv
import hashlib
import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.application.exporting import (
    CSV_ENCODING, EXPORT_SCHEMA_VERSION, StudyExportService, validate_xlsx,
)
from app.config import DataMode
from app.domain import (
    AcquisitionSettings, DataQuality, Event, EventCategory, MonitoringSession,
    Patient, Study, TrendAggregate,
)
from app.storage import AcquisitionRecordingStore, Database, RepositoryBundle


NOW = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)


class ExportingTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = Database(root / "eit.sqlite3", DataMode.SIMULATION)
        self.repositories = RepositoryBundle.build(self.database)
        self.store = AcquisitionRecordingStore(root / "recordings", simulated=True)
        self.service = StudyExportService(self.repositories, self.store)
        self.patient1, self.study1 = self._make_study("P-001", "Иванов")
        self.patient2, self.study2 = self._make_study("P-002", "Петров")
        session = MonitoringSession(study_id=self.study1.id, started_at_utc=NOW, simulated=True)
        self.repositories.sessions.save(session)
        self.repositories.events.append(self.study1.id, Event(
            study_id=self.study1.id, session_id=session.id, occurred_at_utc=NOW,
            category=EventCategory.MARKER, text="Поворот", simulated=True,
            created_at_utc=NOW,
        ))
        self.repositories.trends.append(TrendAggregate(
            study_id=self.study1.id, session_id=session.id,
            interval_start_utc=NOW, interval_end_utc=NOW + timedelta(seconds=15),
            position_seconds=0, aggregation_kind="interval", sample_count=10,
            global_value=2.5, right_value=1.2, left_value=1.3,
            roi_values=(1.0,) * 8, respiratory_rate_bpm=15,
            quality=DataQuality.VALID, algorithm_version="trend-v1", simulated=True,
        ))

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def _make_study(self, external_id, family_name):
        patient = Patient(external_id=external_id, family_name=family_name,
                          created_at_utc=NOW, updated_at_utc=NOW)
        study = Study(patient_id=patient.id, settings=AcquisitionSettings(),
                      simulated=True, created_at_utc=NOW, updated_at_utc=NOW)
        self.repositories.patients.save(patient)
        self.repositories.studies.save(study)
        return patient, study

    def test_json_contains_only_selected_study_and_categories_with_valid_manifest(self):
        result = self.service.export(
            Path(self.temp.name) / "out", "json", [self.study1.id],
            ["metadata", "events"], now_utc=NOW,
        )
        payload = json.loads(result.files[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], EXPORT_SCHEMA_VERSION)
        self.assertEqual([item["study_id"] for item in payload["studies"]], [str(self.study1.id)])
        self.assertEqual(set(payload["studies"][0]), {"study_id", "metadata", "events"})
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["files"][0]["sha256"], hashlib.sha256(result.files[0].read_bytes()).hexdigest())
        self.assertFalse(any(path.name.startswith(".eit_export") for path in result.directory.parent.iterdir()))

    def test_csv_contract_uses_utf8_bom_semicolon_iso_dates_and_dot_decimals(self):
        result = self.service.export(
            Path(self.temp.name) / "csv", "csv", [self.study1.id],
            ["trends"], now_utc=NOW,
        )
        raw = result.files[0].read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.DictReader(io.StringIO(raw.decode(CSV_ENCODING)), delimiter=";"))
        self.assertEqual(rows[0]["global_value"], "2.5")
        self.assertEqual(rows[0]["interval_start_utc"], "2026-10-27T08:00:00Z")

    def test_excel_has_separate_selected_sheets_and_valid_ooxml(self):
        result = self.service.export(
            Path(self.temp.name) / "xlsx", "excel", [self.study1.id],
            ["metadata", "metrics", "events", "trends"], now_utc=NOW,
        )
        validate_xlsx(result.files[0])
        import zipfile
        with zipfile.ZipFile(result.files[0]) as book:
            workbook = book.read("xl/workbook.xml").decode("utf-8")
        for title in ("metadata", "metrics", "events", "trends"):
            self.assertIn(f'name="{title}"', workbook)

    def test_estimate_marks_metadata_as_personal_data(self):
        estimate = self.service.estimate([self.study1.id, self.study2.id], ["metadata"])
        self.assertEqual(estimate.study_count, 2)
        self.assertGreater(estimate.estimated_bytes, 0)
        self.assertTrue(estimate.contains_personal_data)


if __name__ == "__main__":
    unittest.main()
