"""Study lifecycle and the single current-study application context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable
from uuid import UUID

from .events import ApplicationEvent, EventBus, EventType
from .ports import (
    MonitoringSessionRepository,
    PatientRepository,
    SettingsRepository,
    StudyRepository,
)
from ..domain import (
    AcquisitionSettings,
    CalibrationRecord,
    MonitoringSession,
    Study,
    StudyStatus,
    utc_now,
)


SELECTED_PATIENT_SETTING = "selected_patient_id"
CURRENT_STUDY_SETTING = "current_study_id"
OPERATOR_NAME_SETTING = "operator_name"
DEFAULT_OPERATOR_NAME = "local-operator"


class StudyLifecycleError(RuntimeError):
    pass


class InvalidStudyTransition(StudyLifecycleError):
    pass


@dataclass(frozen=True, slots=True)
class StudyHistoryEntry:
    study: Study
    session: MonitoringSession | None
    duration_seconds: float


class StudyLifecycleService:
    """Owns the selected patient, current study and its single MVP session."""

    def __init__(
        self,
        patients: PatientRepository,
        studies: StudyRepository,
        sessions: MonitoringSessionRepository,
        settings: SettingsRepository,
        event_bus: EventBus,
        *,
        simulated: bool,
        clock: Callable[[], datetime] = utc_now,
        settings_provider: Callable[[], AcquisitionSettings] = AcquisitionSettings,
        settings_applier: Callable[[AcquisitionSettings], None] | None = None,
    ) -> None:
        self._patients = patients
        self._studies = studies
        self._sessions = sessions
        self._settings = settings
        self._event_bus = event_bus
        self._simulated = simulated
        self._clock = clock
        self._settings_provider = settings_provider
        self._settings_applier = settings_applier
        self._start_validator: Callable[[], None] | None = None
        self._selected_patient_id: UUID | None = None
        self._study: Study | None = None
        self._session: MonitoringSession | None = None
        self._restore_context()

    @property
    def selected_patient_id(self) -> UUID | None:
        return self._selected_patient_id

    @property
    def current_study(self) -> Study | None:
        return self._study

    @property
    def current_session(self) -> MonitoringSession | None:
        return self._session

    @property
    def status(self) -> StudyStatus | None:
        return None if self._study is None else self._study.status

    @property
    def is_running(self) -> bool:
        return self.status is StudyStatus.RUNNING

    def select_patient(self, patient_id: UUID) -> None:
        if self._patients.get(patient_id) is None:
            raise StudyLifecycleError("patient does not exist")
        if (
            self._study is not None
            and self._study.status in {StudyStatus.RUNNING, StudyStatus.PAUSED}
            and self._study.patient_id != patient_id
        ):
            raise StudyLifecycleError("cannot change patient during an active study")
        self._selected_patient_id = patient_id
        self._settings.save({SELECTED_PATIENT_SETTING: str(patient_id)})
        self._publish()

    def create_study(
        self,
        settings: AcquisitionSettings | None = None,
        *,
        author: str | None = None,
    ) -> Study:
        if self._selected_patient_id is None:
            raise StudyLifecycleError("select a patient before creating a study")
        if self._study is not None and self._study.status in {
            StudyStatus.DRAFT, StudyStatus.READY, StudyStatus.RUNNING, StudyStatus.PAUSED,
        }:
            raise StudyLifecycleError("finish the current study before creating another")
        configured_author = author or self._settings.load().get(
            OPERATOR_NAME_SETTING, DEFAULT_OPERATOR_NAME
        )
        now = self._clock()
        study = Study(
            patient_id=self._selected_patient_id,
            # A frozen value is copied into the study. Later preference changes
            # therefore cannot alter the acquisition parameters of this record.
            settings=settings or self._settings_provider(),
            status=StudyStatus.DRAFT,
            simulated=self._simulated,
            author=str(configured_author),
            created_at_utc=now,
            updated_at_utc=now,
        )
        self._studies.save(study)
        self._study = study
        self._session = None
        self._settings.save({CURRENT_STUDY_SETTING: str(study.id)})
        self._publish()
        return study

    def prepare(self) -> Study:
        if self._study is None or self._study.status is not StudyStatus.DRAFT:
            raise InvalidStudyTransition("only a draft study can be prepared")
        if self._settings_applier is not None:
            self._settings_applier(self._study.settings)
        return self._transition({StudyStatus.DRAFT}, StudyStatus.READY)

    def start(self) -> Study:
        if self.status is not StudyStatus.READY or self._study is None:
            raise InvalidStudyTransition("only a ready study can be started")
        if self._start_validator is not None:
            self._start_validator()
        now = self._clock()
        session = MonitoringSession(
            study_id=self._study.id,
            started_at_utc=now,
            simulated=self._simulated,
        )
        self._sessions.save(session)
        self._session = session
        return self._transition({StudyStatus.READY}, StudyStatus.RUNNING, now=now)

    def set_start_validator(self, validator: Callable[[], None] | None) -> None:
        self._start_validator = validator

    def save_calibration(self, calibration: CalibrationRecord) -> Study:
        if self._study is None or self._study.status not in {
            StudyStatus.DRAFT, StudyStatus.READY
        }:
            raise StudyLifecycleError("calibration requires a draft or ready study")
        self._study = replace(
            self._study,
            calibration=calibration,
            updated_at_utc=self._clock(),
        )
        self._studies.save(self._study)
        self._publish()
        return self._study

    def pause(self) -> Study:
        if self.status is not StudyStatus.RUNNING or self._session is None:
            raise InvalidStudyTransition("only a running study can be paused")
        now = self._clock()
        self._session = replace(self._session, paused_at_utc=now)
        self._sessions.save(self._session)
        return self._transition({StudyStatus.RUNNING}, StudyStatus.PAUSED, now=now)

    def resume(self) -> Study:
        if self.status is not StudyStatus.PAUSED or self._session is None:
            raise InvalidStudyTransition("only a paused study can be resumed")
        now = self._clock()
        paused_at = self._session.paused_at_utc
        if paused_at is None:
            raise StudyLifecycleError("paused study has no pause timestamp")
        pause_seconds = max(0.0, (now - paused_at).total_seconds())
        self._session = replace(
            self._session,
            paused_at_utc=None,
            accumulated_pause_seconds=(
                self._session.accumulated_pause_seconds + pause_seconds
            ),
        )
        self._sessions.save(self._session)
        return self._transition({StudyStatus.PAUSED}, StudyStatus.RUNNING, now=now)

    def stop(self, *, conclusion: str | None = None) -> Study:
        if self.status not in {StudyStatus.RUNNING, StudyStatus.PAUSED}:
            raise InvalidStudyTransition("only an active study can be completed")
        now = self._clock()
        self._finish_session(now)
        return self._transition(
            {StudyStatus.RUNNING, StudyStatus.PAUSED},
            StudyStatus.COMPLETED,
            now=now,
            conclusion=conclusion or "operator_conclusion_not_provided",
        )

    def fail(self, *, reason: str | None = None) -> Study:
        if self.status not in {StudyStatus.READY, StudyStatus.RUNNING, StudyStatus.PAUSED}:
            raise InvalidStudyTransition("only a prepared or active study can fail")
        now = self._clock()
        if self._session is not None:
            self._finish_session(now)
        return self._transition(
            {StudyStatus.READY, StudyStatus.RUNNING, StudyStatus.PAUSED},
            StudyStatus.FAILED,
            now=now,
            conclusion=reason or "emergency_termination",
        )

    def open_study(self, study_id: UUID) -> Study:
        study = self._studies.get(study_id)
        if study is None:
            raise StudyLifecycleError("study does not exist")
        if self.status in {StudyStatus.RUNNING, StudyStatus.PAUSED} and self._study.id != study_id:
            raise StudyLifecycleError("cannot open another study while monitoring is active")
        self._study = study
        self._session = self._sessions.get_for_study(study.id)
        self._selected_patient_id = study.patient_id
        self._settings.save({
            CURRENT_STUDY_SETTING: str(study.id),
            SELECTED_PATIENT_SETTING: str(study.patient_id),
        })
        self._publish()
        return study

    def list_history(self, patient_id: UUID) -> tuple[StudyHistoryEntry, ...]:
        if self._patients.get(patient_id) is None:
            return ()
        result: list[StudyHistoryEntry] = []
        for study in reversed(tuple(self._studies.list_for_patient(patient_id))):
            session = self._sessions.get_for_study(study.id)
            duration = session.duration_seconds(self._clock()) if session else 0.0
            result.append(StudyHistoryEntry(study, session, duration))
        return tuple(result)

    def _transition(
        self,
        allowed: set[StudyStatus],
        target: StudyStatus,
        *,
        now: datetime | None = None,
        conclusion: str | None = None,
    ) -> Study:
        if self._study is None or self._study.status not in allowed:
            current = None if self._study is None else self._study.status.value
            raise InvalidStudyTransition(f"transition {current!r} -> {target.value!r} is not allowed")
        self._study = replace(
            self._study,
            status=target,
            updated_at_utc=now or self._clock(),
            conclusion=conclusion if conclusion is not None else self._study.conclusion,
        )
        self._studies.save(self._study)
        self._publish()
        return self._study

    def _finish_session(self, now: datetime) -> None:
        if self._session is None:
            return
        accumulated = self._session.accumulated_pause_seconds
        if self._session.paused_at_utc is not None:
            accumulated += max(0.0, (now - self._session.paused_at_utc).total_seconds())
        self._session = replace(
            self._session,
            ended_at_utc=now,
            paused_at_utc=None,
            accumulated_pause_seconds=accumulated,
        )
        self._sessions.save(self._session)

    def _restore_context(self) -> None:
        values = self._settings.load()
        self._selected_patient_id = self._valid_patient_id(values.get(SELECTED_PATIENT_SETTING))
        study_id = self._uuid_or_none(values.get(CURRENT_STUDY_SETTING))
        self._study = self._studies.get(study_id) if study_id is not None else None
        self._session = (
            self._sessions.get_for_study(self._study.id) if self._study is not None else None
        )
        if self._study is not None:
            self._selected_patient_id = self._study.patient_id
        if self.status in {StudyStatus.RUNNING, StudyStatus.PAUSED}:
            self.fail(reason="interrupted_by_application_restart")

    def _valid_patient_id(self, value: object) -> UUID | None:
        patient_id = self._uuid_or_none(value)
        return patient_id if patient_id and self._patients.get(patient_id) else None

    @staticmethod
    def _uuid_or_none(value: object) -> UUID | None:
        try:
            return UUID(str(value)) if value else None
        except (TypeError, ValueError):
            return None

    def _publish(self) -> None:
        self._event_bus.publish(ApplicationEvent(
            EventType.STUDY_CHANGED,
            payload={
                "patient_id": str(self._selected_patient_id) if self._selected_patient_id else None,
                "study_id": str(self._study.id) if self._study else None,
                "status": self._study.status.value if self._study else None,
            },
        ))
