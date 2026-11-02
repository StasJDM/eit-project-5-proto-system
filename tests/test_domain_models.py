import unittest
from datetime import date, datetime, timedelta, timezone
import json
from uuid import UUID, uuid4

from app.domain import (
    CURRENT_FORMAT_VERSION,
    AcquisitionSettings,
    Alarm,
    AlarmSeverity,
    AlarmStatus,
    DataQuality,
    EITFrame,
    Event,
    EventCategory,
    MetricSnapshot,
    MonitoringSession,
    Patient,
    Report,
    ReportStatus,
    Study,
    StudyStatus,
    deserialize_model,
    serialize_model,
)


def valid_frame(**overrides):
    values = {
        "sequence_number": 0,
        "timestamp_utc": datetime(2026, 10, 19, tzinfo=timezone.utc),
        "belt_index": 0,
        "global_impedance": 1.0,
        "roi_impedance": (1.0,) * 8,
        "reconstructed_delta_z": ((0.0, 1.0), (1.0, 0.0)),
        "quality": DataQuality.VALID,
        "simulated": True,
    }
    values.update(overrides)
    return EITFrame(**values)


class DomainModelsTest(unittest.TestCase):
    def test_mvp_settings_keep_explicit_belt_and_electrode_counts(self):
        settings = AcquisitionSettings()

        self.assertEqual(settings.belt_count, 1)
        self.assertEqual(settings.electrode_count, 16)
        self.assertEqual(settings.sample_rate_hz, 25.0)

    def test_frame_requires_exactly_eight_roi_values(self):
        with self.assertRaises(ValueError):
            valid_frame(roi_impedance=(1.0,) * 7)

    def test_frame_requires_utc_timestamp(self):
        with self.assertRaises(ValueError):
            valid_frame(timestamp_utc=datetime(2026, 10, 19))
        with self.assertRaises(ValueError):
            valid_frame(
                timestamp_utc=datetime(
                    2026, 10, 19, tzinfo=timezone(timedelta(hours=3))
                )
            )

    def test_frame_requires_rectangular_map(self):
        with self.assertRaises(ValueError):
            valid_frame(reconstructed_delta_z=((0.0,), (0.0, 1.0)))

    def test_all_task_3_models_round_trip_through_json(self):
        timestamp = datetime(2026, 10, 19, 12, 30, tzinfo=timezone.utc)
        patient = Patient(
            external_id="P-001",
            medical_record_number="MR-001",
            family_name="Иванов",
            given_name="Иван",
            date_of_birth=date(1980, 1, 2),
            sex="male",
            weight_kg=75.5,
            height_cm=180.0,
            chest_circumference_cm=96.0,
            created_at_utc=timestamp,
            updated_at_utc=timestamp,
        )
        study = Study(
            patient_id=patient.id,
            settings=AcquisitionSettings(),
            status=StudyStatus.READY,
            simulated=True,
            author="operator",
            created_at_utc=timestamp,
            updated_at_utc=timestamp,
        )
        session = MonitoringSession(
            study_id=study.id,
            started_at_utc=timestamp,
            ended_at_utc=timestamp + timedelta(minutes=5),
            simulated=True,
        )
        frame = valid_frame(sequence_number=42, timestamp_utc=timestamp)
        metrics = MetricSnapshot(
            study_id=study.id,
            session_id=session.id,
            timestamp_utc=timestamp,
            respiratory_rate_bpm=15.0,
            tvi_au=1.0,
            eeli_au=0.45,
            eili_au=1.45,
            right_left_ratio=1.08,
            ventral_dorsal_ratio=0.85,
            roi_tvi_au=(0.1,) * 8,
            quality=DataQuality.VALID,
            algorithm_version="metrics-v1",
            simulated=True,
        )
        event = Event(
            study_id=study.id,
            session_id=session.id,
            occurred_at_utc=timestamp,
            category=EventCategory.MARKER,
            text="Изменено положение пациента",
            created_at_utc=timestamp,
            simulated=True,
        )
        alarm = Alarm(
            study_id=study.id,
            session_id=session.id,
            code="SIGNAL_QUALITY",
            severity=AlarmSeverity.WARNING,
            status=AlarmStatus.ACKNOWLEDGED,
            activated_at_utc=timestamp,
            updated_at_utc=timestamp + timedelta(seconds=2),
            acknowledged_at_utc=timestamp + timedelta(seconds=2),
            simulated=True,
        )
        report = Report(
            study_id=study.id,
            period_start_utc=timestamp,
            period_end_utc=timestamp + timedelta(minutes=5),
            status=ReportStatus.GENERATED,
            template_version="report-v1",
            algorithm_versions=("metrics-v1",),
            created_at_utc=timestamp + timedelta(minutes=5),
            file_name="report.pdf",
            checksum_sha256="a" * 64,
            simulated=True,
        )

        for model in (patient, study, session, frame, metrics, event, alarm, report):
            with self.subTest(model=type(model).__name__):
                encoded = json.loads(json.dumps(serialize_model(model)))
                self.assertEqual(deserialize_model(encoded), model)
                self.assertEqual(encoded["format_version"], CURRENT_FORMAT_VERSION)

    def test_required_entities_receive_unique_uuid_identifiers(self):
        patient_a = Patient()
        patient_b = Patient()
        study_a = Study(patient_id=patient_a.id, settings=AcquisitionSettings())
        study_b = Study(patient_id=patient_a.id, settings=AcquisitionSettings())
        session_a = MonitoringSession(study_id=study_a.id)
        session_b = MonitoringSession(study_id=study_a.id)
        now = datetime(2026, 10, 19, tzinfo=timezone.utc)
        event_a = Event(
            study_id=study_a.id,
            session_id=session_a.id,
            occurred_at_utc=now,
            category=EventCategory.MARKER,
            text="A",
        )
        event_b = Event(
            study_id=study_a.id,
            session_id=session_a.id,
            occurred_at_utc=now,
            category=EventCategory.MARKER,
            text="B",
        )

        identifiers = {
            patient_a.id,
            patient_b.id,
            study_a.id,
            study_b.id,
            session_a.id,
            session_b.id,
            event_a.id,
            event_b.id,
        }
        self.assertEqual(len(identifiers), 8)
        self.assertTrue(all(isinstance(identifier, UUID) for identifier in identifiers))

    def test_metric_snapshot_can_explicitly_represent_unavailable_values(self):
        snapshot = MetricSnapshot(
            study_id=uuid4(),
            session_id=uuid4(),
            timestamp_utc=datetime(2026, 10, 19, tzinfo=timezone.utc),
            respiratory_rate_bpm=None,
            tvi_au=None,
            eeli_au=None,
            eili_au=None,
            right_left_ratio=None,
            ventral_dorsal_ratio=None,
            roi_tvi_au=(None,) * 8,
            quality=DataQuality.UNAVAILABLE,
            quality_reason="insufficient_signal",
            algorithm_version="metrics-v1",
            simulated=False,
        )

        self.assertEqual(snapshot.quality, DataQuality.UNAVAILABLE)
        self.assertIsNone(snapshot.respiratory_rate_bpm)

    def test_metric_snapshot_reads_legacy_roi_tiv_key(self):
        snapshot = MetricSnapshot(
            study_id=uuid4(),
            session_id=uuid4(),
            timestamp_utc=datetime(2026, 10, 19, tzinfo=timezone.utc),
            respiratory_rate_bpm=15.0,
            tvi_au=1.0,
            eeli_au=0.5,
            eili_au=1.5,
            right_left_ratio=1.0,
            ventral_dorsal_ratio=1.0,
            roi_tvi_au=(0.125,) * 8,
            quality=DataQuality.VALID,
            algorithm_version="metrics-v1",
            simulated=False,
        )
        encoded = serialize_model(snapshot)
        encoded["roi_tiv_au"] = encoded.pop("roi_tvi_au")

        self.assertEqual(deserialize_model(encoded), snapshot)

    def test_session_and_report_reject_reversed_time_intervals(self):
        later = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)
        earlier = later - timedelta(minutes=1)
        with self.assertRaises(ValueError):
            MonitoringSession(
                study_id=uuid4(),
                started_at_utc=later,
                ended_at_utc=earlier,
            )
        with self.assertRaises(ValueError):
            Report(
                study_id=uuid4(),
                period_start_utc=later,
                period_end_utc=earlier,
                status=ReportStatus.DRAFT,
                template_version="v1",
                algorithm_versions=("v1",),
            )

    def test_deserializer_rejects_unknown_format_version(self):
        encoded = serialize_model(Patient())
        encoded["format_version"] = CURRENT_FORMAT_VERSION + 1

        with self.assertRaisesRegex(ValueError, "unsupported format_version"):
            deserialize_model(encoded)


if __name__ == "__main__":
    unittest.main()
