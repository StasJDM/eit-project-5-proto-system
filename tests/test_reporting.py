import json
import hashlib
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.application.reporting import MedicalReportService, REPORT_TEMPLATE_VERSION, ReportError
from app.config import DataMode
from app.domain import (
    AcquisitionSettings, DataQuality, Event, EventCategory, MonitoringSession,
    Patient, Study, TrendAggregate,
)
from app.storage import Database, RepositoryBundle


NOW = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)


class ReportingTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "db.sqlite3", DataMode.SIMULATION)
        self.repositories = RepositoryBundle.build(self.database)
        self.service = MedicalReportService(self.repositories)
        self.patient = Patient(external_id="P-900", family_name="Иванов", given_name="Иван",
                               created_at_utc=NOW, updated_at_utc=NOW)
        self.study = Study(patient_id=self.patient.id, settings=AcquisitionSettings(),
                           simulated=True, created_at_utc=NOW, updated_at_utc=NOW + timedelta(minutes=10))
        self.session = MonitoringSession(study_id=self.study.id, started_at_utc=NOW,
                                         ended_at_utc=NOW + timedelta(minutes=10), simulated=True)
        self.repositories.patients.save(self.patient)
        self.repositories.studies.save(self.study)
        self.repositories.sessions.save(self.session)
        self.repositories.trends.append(TrendAggregate(
            study_id=self.study.id, session_id=self.session.id,
            interval_start_utc=NOW + timedelta(minutes=1), interval_end_utc=NOW + timedelta(minutes=2),
            position_seconds=60, aggregation_kind="interval", sample_count=20,
            global_value=10, right_value=6, left_value=4, roi_values=(1,2,3,4,5,6,7,8),
            respiratory_rate_bpm=16, quality=DataQuality.VALID,
            algorithm_version="trend-v1", simulated=True,
        ))
        self.repositories.events.append(self.study.id, Event(
            study_id=self.study.id, session_id=self.session.id,
            occurred_at_utc=NOW + timedelta(minutes=3), category=EventCategory.ADVERSE_EVENT,
            text="Кашель", author="operator", created_at_utc=NOW + timedelta(minutes=3),
            simulated=True,
        ))

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_snapshot_uses_persisted_values_and_remains_reproducible(self):
        report = self.service.create(
            self.study.id, NOW, NOW + timedelta(minutes=5), title="Контрольный отчёт",
            created_at_utc=NOW + timedelta(minutes=6),
        )
        snapshot = json.loads(report.snapshot_json)
        self.assertEqual(report.template_version, REPORT_TEMPLATE_VERSION)
        self.assertEqual(snapshot["summary"]["respiratory_rate_bpm_mean"], 16)
        self.assertEqual(snapshot["summary"]["right_left_ratio"], 1.5)
        self.assertEqual(snapshot["summary"]["roi_means"], [1,2,3,4,5,6,7,8])
        self.assertEqual(snapshot["events"][0]["text"], "Кашель")
        self.assertEqual(snapshot["breathing"]["type"], "undetermined")
        original = report.snapshot_json
        self.repositories.events.append(self.study.id, Event(
            study_id=self.study.id, session_id=self.session.id,
            occurred_at_utc=NOW + timedelta(minutes=4), category=EventCategory.MARKER,
            text="Позднее событие", created_at_utc=NOW + timedelta(minutes=4), simulated=True,
        ))
        self.assertEqual(self.repositories.reports.get(report.id).snapshot_json, original)
        self.assertNotIn("Позднее событие", self.service.render_text(report.id))

    def test_period_is_validated_against_session(self):
        with self.assertRaises(ReportError):
            self.service.create(self.study.id, NOW + timedelta(minutes=5), NOW, title="x")
        with self.assertRaises(ReportError):
            self.service.create(
                self.study.id, NOW + timedelta(days=1), NOW + timedelta(days=1, minutes=1), title="x"
            )

    def test_pdf_is_searchable_and_file_reference_checksum_are_persisted(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        report = self.service.create(
            self.study.id, NOW, NOW + timedelta(minutes=5), title="Отчёт ЭИТ",
            language="ru", created_at_utc=NOW + timedelta(minutes=6),
        )
        target = Path(self.temp.name) / "report.pdf"
        updated = self.service.generate_pdf(report, target, software_version="test-1.2.3")
        self.assertTrue(target.read_bytes().startswith(b"%PDF"))
        self.assertEqual(updated.file_name, str(target))
        self.assertEqual(updated.checksum_sha256, hashlib.sha256(target.read_bytes()).hexdigest())
        import pdfplumber
        with pdfplumber.open(target) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        self.assertIn("Отчёт ЭИТ", text)
        self.assertIn(str(self.study.id), text)
        self.assertIn("1/1", text)

    def test_html_uses_localized_labels_for_all_supported_report_languages(self):
        samples = {"ru": "Пациент", "en": "Patient", "zh": "患者", "vi": "Bệnh nhân"}
        for language, expected in samples.items():
            with self.subTest(language=language):
                report = self.service.create(
                    self.study.id, NOW, NOW + timedelta(minutes=5),
                    title=f"report-{language}", language=language,
                )
                self.assertIn(expected, self.service.render_html(report))


if __name__ == "__main__":
    unittest.main()
