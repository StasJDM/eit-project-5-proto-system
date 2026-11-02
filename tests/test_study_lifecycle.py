import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.application import (
    EventBus,
    EventType,
    InvalidStudyTransition,
    StudyLifecycleError,
    StudyLifecycleService,
)
from app.config import DataMode
from app.domain import AcquisitionSettings, Patient, StudyStatus
from app.storage import Database, RepositoryBundle


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 25, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value

    def advance(self, seconds: int):
        self.value += timedelta(seconds=seconds)


class StudyLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "study.sqlite3", DataMode.SIMULATION)
        self.repositories = RepositoryBundle.build(self.database)
        self.patient = Patient(external_id="P-1")
        self.repositories.patients.save(self.patient)
        self.clock = Clock()
        self.bus = EventBus()
        self.events = []
        self.bus.subscribe(EventType.STUDY_CHANGED, self.events.append)
        self.service = StudyLifecycleService(
            self.repositories.patients,
            self.repositories.studies,
            self.repositories.sessions,
            self.repositories.settings,
            self.bus,
            simulated=True,
            clock=self.clock,
        )

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_study_requires_selected_patient_and_persists_author_settings_and_states(self):
        with self.assertRaises(StudyLifecycleError):
            self.service.create_study()

        self.service.select_patient(self.patient.id)
        settings = AcquisitionSettings(sample_rate_hz=25.0)
        draft = self.service.create_study(settings, author="operator-1")
        self.assertEqual(draft.status, StudyStatus.DRAFT)
        self.assertEqual(draft.patient_id, self.patient.id)
        self.assertEqual(draft.author, "operator-1")
        self.assertEqual(draft.settings, settings)

        ready = self.service.prepare()
        self.assertEqual(ready.status, StudyStatus.READY)
        running = self.service.start()
        self.assertEqual(running.status, StudyStatus.RUNNING)
        self.assertIsNotNone(self.service.current_session)

        self.clock.advance(10)
        self.service.pause()
        self.clock.advance(20)
        self.service.resume()
        self.clock.advance(15)
        completed = self.service.stop(conclusion="stable")

        self.assertEqual(completed.status, StudyStatus.COMPLETED)
        self.assertEqual(completed.conclusion, "stable")
        self.assertEqual(self.service.current_session.duration_seconds(), 25.0)
        self.assertEqual(self.repositories.studies.get(draft.id), completed)
        self.assertEqual(
            self.repositories.sessions.get_for_study(draft.id),
            self.service.current_session,
        )
        self.assertEqual(self.events[-1].payload["status"], "completed")

    def test_invalid_transitions_and_terminal_mutation_are_rejected(self):
        self.service.select_patient(self.patient.id)
        self.service.create_study()
        with self.assertRaises(InvalidStudyTransition):
            self.service.start()
        self.service.prepare()
        with self.assertRaises(InvalidStudyTransition):
            self.service.resume()
        self.service.start()
        self.service.stop()
        for command in (self.service.start, self.service.pause, self.service.resume, self.service.stop):
            with self.subTest(command=command.__name__):
                with self.assertRaises(InvalidStudyTransition):
                    command()

    def test_restart_marks_unfinished_study_failed_instead_of_resuming(self):
        self.service.select_patient(self.patient.id)
        study = self.service.create_study()
        self.service.prepare()
        self.service.start()
        self.clock.advance(12)

        restored = StudyLifecycleService(
            self.repositories.patients,
            self.repositories.studies,
            self.repositories.sessions,
            self.repositories.settings,
            EventBus(),
            simulated=True,
            clock=self.clock,
        )

        self.assertEqual(restored.current_study.id, study.id)
        self.assertEqual(restored.status, StudyStatus.FAILED)
        self.assertEqual(restored.current_study.conclusion, "interrupted_by_application_restart")
        self.assertEqual(restored.current_session.duration_seconds(), 12.0)

    def test_completed_study_can_only_be_opened_for_viewing(self):
        self.service.select_patient(self.patient.id)
        study = self.service.create_study()
        self.service.prepare()
        self.service.start()
        self.service.stop()

        opened = self.service.open_study(study.id)

        self.assertEqual(opened.status, StudyStatus.COMPLETED)
        with self.assertRaises(InvalidStudyTransition):
            self.service.prepare()

    def test_completed_study_appears_only_in_correct_patient_history(self):
        other_patient = Patient(external_id="P-2")
        self.repositories.patients.save(other_patient)
        self.service.select_patient(self.patient.id)
        study = self.service.create_study(author="operator-history")
        self.service.prepare()
        self.service.start()
        self.clock.advance(37)
        self.service.stop(conclusion="No acute changes")

        history = self.service.list_history(self.patient.id)

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].study.id, study.id)
        self.assertEqual(history[0].study.status, StudyStatus.COMPLETED)
        self.assertEqual(history[0].duration_seconds, 37.0)
        self.assertEqual(history[0].study.conclusion, "No acute changes")
        self.assertEqual(self.service.list_history(other_patient.id), ())


if __name__ == "__main__":
    unittest.main()
