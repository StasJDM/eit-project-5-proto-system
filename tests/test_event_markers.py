import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

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

            clock.advance(5)
            correction = service.correct(
                marker.id, "Кашель во время санации", "doctor-b"
            )
            self.assertEqual(correction.corrects_event_id, marker.id)
            self.assertEqual(correction.position_seconds, marker.position_seconds)
            self.assertEqual(service.list_for_current_study(), (marker, correction))
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
                self.assertEqual(restored.list_for_current_study(), (marker, correction))
                self.assertEqual(
                    restored.markers_between(12.0, 13.0), (marker, correction)
                )
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
