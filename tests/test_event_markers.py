import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.application import EventBus, EventMarkerService, StudyLifecycleService
from app.config import DataMode
from app.domain import EventCategory, Patient
from app.storage import Database, RepositoryBundle


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds: float):
        self.value += timedelta(seconds=seconds)


class EventMarkerServiceTest(unittest.TestCase):
    def test_legacy_default_author_is_displayed_as_operator(self):
        lifecycle = SimpleNamespace(
            current_study=SimpleNamespace(author="local-operator")
        )
        service = EventMarkerService(None, lifecycle, EventBus())

        self.assertEqual(service.default_author, "Оператор")

    def test_marker_position_metadata_correction_and_restart_persistence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "markers.sqlite3"
            database = Database(path, DataMode.SIMULATION)
            repositories = RepositoryBundle.build(database)
            clock = Clock()
            lifecycle = StudyLifecycleService(
                repositories.patients,
                repositories.studies,
                repositories.sessions,
                repositories.settings,
                EventBus(),
                simulated=True,
                clock=clock,
            )
            patient = Patient(external_id="MARKER-1")
            repositories.patients.save(patient)
            lifecycle.select_patient(patient.id)
            lifecycle.create_study(author="doctor-a")
            lifecycle.prepare()
            lifecycle.start()
            clock.advance(12.25)
            service = EventMarkerService(
                repositories.events, lifecycle, EventBus(), clock=clock
            )

            marker = service.create("cough", "Кашель", "doctor-a")
            self.assertEqual(marker.category, EventCategory.MARKER)
            self.assertEqual(marker.event_type, "cough")
            self.assertEqual(marker.author, "doctor-a")
            self.assertAlmostEqual(marker.position_seconds, 12.25)

            clock.advance(0.25)
            marker_without_description = service.create(
                "procedure", "   ", "doctor-a"
            )
            self.assertEqual(marker_without_description.text, "")

            clock.advance(5)
            correction = service.correct(
                marker.id, "", "doctor-b"
            )
            self.assertEqual(correction.corrects_event_id, marker.id)
            self.assertEqual(correction.position_seconds, marker.position_seconds)
            self.assertEqual(correction.text, "")
            self.assertEqual(
                service.list_for_current_study(),
                (marker, marker_without_description, correction),
            )
            lifecycle.stop()
            study_id = lifecycle.current_study.id
            database.close()

            reopened = Database(path, DataMode.SIMULATION)
            loaded = RepositoryBundle.build(reopened)
            restored_lifecycle = StudyLifecycleService(
                loaded.patients,
                loaded.studies,
                loaded.sessions,
                loaded.settings,
                EventBus(),
                simulated=True,
                clock=clock,
            )
            restored = EventMarkerService(
                loaded.events, restored_lifecycle, EventBus(), clock=clock
            )
            try:
                self.assertEqual(restored_lifecycle.current_study.id, study_id)
                self.assertEqual(
                    restored.list_for_current_study(),
                    (marker, marker_without_description, correction),
                )
                self.assertEqual(
                    restored.markers_between(12.0, 13.0),
                    (marker, marker_without_description, correction),
                )
            finally:
                reopened.close()

    def test_marker_uses_signal_position_when_playback_speed_differs_from_wall_time(self):
        with TemporaryDirectory() as directory:
            database = Database(Path(directory) / "markers.sqlite3", DataMode.FROMFILE)
            repositories = RepositoryBundle.build(database)
            clock = Clock()
            lifecycle = StudyLifecycleService(
                repositories.patients,
                repositories.studies,
                repositories.sessions,
                repositories.settings,
                EventBus(),
                simulated=True,
                clock=clock,
            )
            patient = Patient(external_id="MARKER-SLOW-PLAYBACK")
            repositories.patients.save(patient)
            lifecycle.select_patient(patient.id)
            lifecycle.create_study(author="doctor-a")
            lifecycle.prepare()
            lifecycle.start()
            clock.advance(10.0)
            service = EventMarkerService(
                repositories.events,
                lifecycle,
                EventBus(),
                clock=clock,
                position_provider=lambda: 5.0,
            )
            try:
                marker = service.create("cough", "", "doctor-a")
                self.assertEqual(service.current_position_seconds, 5.0)
                self.assertEqual(marker.position_seconds, 5.0)
            finally:
                database.close()


if __name__ == "__main__":
    unittest.main()
