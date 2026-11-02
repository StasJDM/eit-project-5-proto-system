from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import app.application
from app.application import AdverseEventError, AdverseEventService, EventBus, StudyLifecycleService
from app.config import DataMode
from app.domain import EventCategory, Patient
from app.storage import Database, RepositoryBundle
from app.screens.reports_screen import _report_text


class _Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


class AdverseEventServiceTest(unittest.TestCase):
    def test_event_and_correction_are_append_only_and_survive_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "simulation.sqlite3"
            db = Database(path, DataMode.SIMULATION)
            repos = RepositoryBundle.build(db)
            patient = Patient()
            repos.patients.save(patient)
            clock = _Clock(datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc))
            bus = EventBus()
            lifecycle = StudyLifecycleService(
                repos.patients, repos.studies, repos.sessions, repos.settings, bus,
                simulated=True, clock=clock,
            )
            lifecycle.select_patient(patient.id)
            lifecycle.create_study(author="operator-1")
            lifecycle.prepare()
            lifecycle.start()
            service = AdverseEventService(repos.events, lifecycle, bus, clock=clock)

            original = service.create(
                "adverse_event", "Desaturation", "operator-1",
                occurred_at_utc=clock.value,
            )
            clock.value += timedelta(seconds=10)
            correction = service.correct(
                original.id, "Desaturation confirmed", "operator-2"
            )
            self.assertEqual(correction.corrects_event_id, original.id)
            self.assertEqual(len(service.list_current(include_markers=False)), 2)
            self.assertIn(
                "Desaturation confirmed",
                _report_text("Report", "Patient", "01.01.2026", service.list_current()),
            )
            with self.assertRaises(AdverseEventError):
                service.create("unknown", "text", "operator-1")
            study_id = lifecycle.current_study.id
            db.close()

            reopened = Database(path, DataMode.SIMULATION)
            persisted = RepositoryBundle.build(reopened).events.search(
                study_id, category=EventCategory.ADVERSE_EVENT.value,
                query="confirmed",
            )
            self.assertEqual([event.id for event in persisted], [correction.id])
            reopened.close()


if __name__ == "__main__":
    unittest.main()
