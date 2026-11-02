"""SQLite schema migrations and typed repositories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Iterator, TypeVar
from uuid import UUID

from ..config import DataMode
from ..domain import (
    Alarm,
    Event,
    MonitoringSession,
    Patient,
    Report,
    Study,
    TrendAggregate,
    deserialize_model,
    serialize_model,
)
from ..technical_logging import get_logger, technical_event


LATEST_SCHEMA_VERSION = 4
_logger = get_logger("storage")


class DatabaseModeError(RuntimeError):
    """Raised when simulation and device records would share one database."""


_MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE patients (
            id TEXT PRIMARY KEY,
            external_id TEXT,
            medical_record_number TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE UNIQUE INDEX ux_patients_external_id
            ON patients(external_id) WHERE external_id IS NOT NULL;
        CREATE INDEX ix_patients_medical_record_number
            ON patients(medical_record_number);

        CREATE TABLE studies (
            id TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE RESTRICT,
            status TEXT NOT NULL,
            simulated INTEGER NOT NULL CHECK(simulated IN (0, 1)),
            created_at_utc TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX ix_studies_patient_created
            ON studies(patient_id, created_at_utc);
        CREATE INDEX ix_studies_status ON studies(status);

        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL
        );
    """,
    2: """
        CREATE TABLE monitoring_sessions (
            id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
            simulated INTEGER NOT NULL CHECK(simulated IN (0, 1)),
            started_at_utc TEXT,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX ix_sessions_study_started
            ON monitoring_sessions(study_id, started_at_utc);

        CREATE TABLE events (
            id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            occurred_at_utc TEXT NOT NULL,
            simulated INTEGER NOT NULL CHECK(simulated IN (0, 1)),
            payload_json TEXT NOT NULL
        );
        CREATE INDEX ix_events_study_time ON events(study_id, occurred_at_utc);
        CREATE INDEX ix_events_session_time ON events(session_id, occurred_at_utc);

        CREATE TABLE alarms (
            id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            severity TEXT NOT NULL,
            activated_at_utc TEXT NOT NULL,
            simulated INTEGER NOT NULL CHECK(simulated IN (0, 1)),
            payload_json TEXT NOT NULL
        );
        CREATE INDEX ix_alarms_study_status ON alarms(study_id, status);

        CREATE TABLE reports (
            id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
            status TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            simulated INTEGER NOT NULL CHECK(simulated IN (0, 1)),
            payload_json TEXT NOT NULL
        );
        CREATE INDEX ix_reports_study_created ON reports(study_id, created_at_utc);
    """,
    3: """
        ALTER TABLE patients ADD COLUMN search_text TEXT NOT NULL DEFAULT '';
        UPDATE patients SET search_text = lower(
            coalesce(external_id, '') || ' ' || coalesce(medical_record_number, '')
        );
        CREATE INDEX ix_patients_search_text ON patients(search_text);
        CREATE UNIQUE INDEX ux_patients_medical_record_number
            ON patients(medical_record_number)
            WHERE medical_record_number IS NOT NULL;
        CREATE UNIQUE INDEX ux_patients_external_id_nocase
            ON patients(external_id COLLATE NOCASE)
            WHERE external_id IS NOT NULL;
    """,
    4: """
        CREATE TABLE trend_aggregates (
            id TEXT PRIMARY KEY,
            study_id TEXT NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL REFERENCES monitoring_sessions(id) ON DELETE CASCADE,
            interval_start_utc TEXT NOT NULL,
            interval_end_utc TEXT NOT NULL,
            position_seconds REAL NOT NULL,
            aggregation_kind TEXT NOT NULL CHECK(aggregation_kind IN ('interval', 'breath_cycle')),
            quality TEXT NOT NULL,
            algorithm_version TEXT NOT NULL,
            simulated INTEGER NOT NULL CHECK(simulated IN (0, 1)),
            payload_json TEXT NOT NULL
        );
        CREATE INDEX ix_trend_aggregates_study_kind_time
            ON trend_aggregates(study_id, aggregation_kind, interval_start_utc);
        CREATE INDEX ix_trend_aggregates_session_time
            ON trend_aggregates(session_id, interval_start_utc);
    """,
}


class Database:
    def __init__(
        self,
        path: Path | str,
        mode: DataMode,
        *,
        target_version: int = LATEST_SCHEMA_VERSION,
    ) -> None:
        self.path = Path(path)
        self.mode = mode
        self._lock = RLock()
        self._closed = False
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # Trend aggregates are produced by the acquisition worker while the UI
        # reads the same database.  SQLite permits this when access to a shared
        # connection is explicitly serialized by the application.
        self.connection = sqlite3.connect(str(path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        try:
            self.migrate(target_version)
            self._validate_mode()
        except Exception:
            self.connection.close()
            raise

    @property
    def simulated(self) -> bool:
        return self.mode in {DataMode.SIMULATION, DataMode.FROMFILE}

    @property
    def schema_version(self) -> int:
        row = self.fetchone(
            "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
        )
        return int(row["version"])

    def migrate(self, target_version: int = LATEST_SCHEMA_VERSION) -> None:
        if target_version < 0 or target_version > LATEST_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema target: {target_version}")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS database_metadata ("
            "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        current = self.schema_version
        for version in range(current + 1, target_version + 1):
            with self.connection:
                for statement in _MIGRATIONS[version].split(";"):
                    if statement.strip():
                        self.connection.execute(statement)
                if version == 3:
                    rows = self.connection.execute(
                        "SELECT id, payload_json FROM patients"
                    ).fetchall()
                    for row in rows:
                        patient = _decode(row["payload_json"], Patient)
                        self.connection.execute(
                            "UPDATE patients SET search_text = ? WHERE id = ?",
                            (_patient_search_text(patient), row["id"]),
                        )
                self.connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at_utc) "
                    "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                    (version,),
                )
            technical_event(
                _logger,
                logging.INFO,
                "database.migrated",
                schema_version=version,
                result="success",
            )

    def _validate_mode(self) -> None:
        row = self.fetchone(
            "SELECT value FROM database_metadata WHERE key = 'data_mode'"
        )
        if row is None:
            with self.connection:
                self.connection.execute(
                    "INSERT INTO database_metadata(key, value) VALUES ('data_mode', ?)",
                    (self.mode.value,),
                )
        elif row["value"] != self.mode.value:
            raise DatabaseModeError(
                f"database belongs to {row['value']!r} mode, not {self.mode.value!r}"
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            with self.connection:
                yield self.connection

    def fetchone(self, query: str, parameters=()):
        with self._lock:
            return self.connection.execute(query, parameters).fetchone()

    def fetchall(self, query: str, parameters=()):
        with self._lock:
            return self.connection.execute(query, parameters).fetchall()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self.connection.close()
            self._closed = True
        technical_event(_logger, logging.INFO, "database.closed")


T = TypeVar("T")


def _payload(model: object) -> str:
    return json.dumps(serialize_model(model), ensure_ascii=False, separators=(",", ":"))


def _decode(payload: str, expected: type[T]) -> T:
    model = deserialize_model(json.loads(payload))
    if not isinstance(model, expected):
        raise TypeError(f"stored payload is {type(model).__name__}, expected {expected.__name__}")
    return model


def _ensure_mode(database: Database, simulated: bool) -> None:
    if simulated != database.simulated:
        raise DatabaseModeError(
            "simulated records must use the simulation database and real records "
            "must use the device database"
        )


class SQLitePatientRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def get(self, patient_id: UUID) -> Patient | None:
        row = self.db.fetchone(
            "SELECT payload_json FROM patients WHERE id = ?", (str(patient_id),)
        )
        return None if row is None else _decode(row["payload_json"], Patient)

    def list(self) -> Sequence[Patient]:
        rows = self.db.fetchall(
            "SELECT payload_json FROM patients ORDER BY id"
        )
        return tuple(_decode(row["payload_json"], Patient) for row in rows)

    def find_by_external_id(self, external_id: str) -> Patient | None:
        row = self.db.fetchone(
            "SELECT payload_json FROM patients WHERE external_id = ? COLLATE NOCASE",
            (external_id,),
        )
        return None if row is None else _decode(row["payload_json"], Patient)

    def find_by_medical_record_number(self, number: str) -> Patient | None:
        row = self.db.fetchone(
            "SELECT payload_json FROM patients WHERE medical_record_number = ?", (number,)
        )
        return None if row is None else _decode(row["payload_json"], Patient)

    def search(self, query: str, *, limit: int = 50) -> Sequence[Patient]:
        if limit <= 0:
            return ()
        normalized = " ".join(query.casefold().split())
        if not normalized:
            rows = self.db.fetchall(
                "SELECT payload_json FROM patients ORDER BY search_text, id LIMIT ?",
                (limit,),
            ) if self.db.schema_version >= 3 else self.db.fetchall(
                "SELECT payload_json FROM patients ORDER BY id LIMIT ?", (limit,)
            )
        elif self.db.schema_version >= 3:
            escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = self.db.fetchall(
                "SELECT payload_json FROM patients WHERE search_text LIKE ? ESCAPE '\\' "
                "ORDER BY search_text, id LIMIT ?",
                (f"%{escaped}%", limit),
            )
        else:
            rows = []
            for patient in self.list():
                if normalized in _patient_search_text(patient):
                    rows.append({"payload_json": _payload(patient)})
                    if len(rows) >= limit:
                        break
        return tuple(_decode(row["payload_json"], Patient) for row in rows)

    def save(self, patient: Patient) -> None:
        with self.db.transaction() as connection:
            if self.db.schema_version >= 3:
                connection.execute(
                    "INSERT INTO patients(id, external_id, medical_record_number, search_text, payload_json) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                    "external_id=excluded.external_id, "
                    "medical_record_number=excluded.medical_record_number, "
                    "search_text=excluded.search_text, payload_json=excluded.payload_json",
                    (
                        str(patient.id), patient.external_id,
                        patient.medical_record_number, _patient_search_text(patient),
                        _payload(patient),
                    ),
                )
            else:
                connection.execute(
                    "INSERT INTO patients(id, external_id, medical_record_number, payload_json) "
                    "VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                    "external_id=excluded.external_id, "
                    "medical_record_number=excluded.medical_record_number, "
                    "payload_json=excluded.payload_json",
                    (str(patient.id), patient.external_id,
                     patient.medical_record_number, _payload(patient)),
                )

    def delete(self, patient_id: UUID) -> None:
        with self.db.transaction() as connection:
            connection.execute("DELETE FROM patients WHERE id = ?", (str(patient_id),))


def _patient_search_text(patient: Patient) -> str:
    return " ".join(
        part.casefold().strip()
        for part in (
            patient.family_name,
            patient.given_name,
            patient.middle_name,
            patient.external_id,
            patient.medical_record_number,
        )
        if part and part.strip()
    )


class SQLiteStudyRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def get(self, study_id: UUID) -> Study | None:
        row = self.db.fetchone(
            "SELECT payload_json FROM studies WHERE id = ?", (str(study_id),)
        )
        return None if row is None else _decode(row["payload_json"], Study)

    def list_for_patient(self, patient_id: UUID) -> Sequence[Study]:
        rows = self.db.fetchall(
            "SELECT payload_json FROM studies WHERE patient_id = ? "
            "ORDER BY created_at_utc, id",
            (str(patient_id),),
        )
        return tuple(_decode(row["payload_json"], Study) for row in rows)

    def list_all(self) -> Sequence[Study]:
        rows = self.db.fetchall(
            "SELECT payload_json FROM studies ORDER BY created_at_utc DESC, id"
        )
        return tuple(_decode(row["payload_json"], Study) for row in rows)

    def save(self, study: Study) -> None:
        _ensure_mode(self.db, study.simulated)
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO studies(id, patient_id, status, simulated, created_at_utc, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "status=excluded.status, payload_json=excluded.payload_json",
                (
                    str(study.id),
                    str(study.patient_id),
                    study.status.value,
                    int(study.simulated),
                    study.created_at_utc.isoformat(),
                    _payload(study),
                ),
            )
        technical_event(
            _logger,
            logging.INFO,
            "study.saved",
            study_id=study.id,
            study_status=study.status.value,
            simulated=study.simulated,
        )

    def delete(self, study_id: UUID) -> None:
        with self.db.transaction() as connection:
            connection.execute("DELETE FROM studies WHERE id = ?", (str(study_id),))


class SQLiteMonitoringSessionRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def get(self, session_id: UUID) -> MonitoringSession | None:
        row = self.db.fetchone(
            "SELECT payload_json FROM monitoring_sessions WHERE id = ?",
            (str(session_id),),
        )
        return None if row is None else _decode(row["payload_json"], MonitoringSession)

    def get_for_study(self, study_id: UUID) -> MonitoringSession | None:
        row = self.db.fetchone(
            "SELECT payload_json FROM monitoring_sessions WHERE study_id = ? "
            "ORDER BY started_at_utc, id LIMIT 1",
            (str(study_id),),
        )
        return None if row is None else _decode(row["payload_json"], MonitoringSession)

    def save(self, session: MonitoringSession) -> None:
        _ensure_mode(self.db, session.simulated)
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO monitoring_sessions(id, study_id, simulated, started_at_utc, payload_json) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json",
                (
                    str(session.id),
                    str(session.study_id),
                    int(session.simulated),
                    session.started_at_utc.isoformat() if session.started_at_utc else None,
                    _payload(session),
                ),
            )
        state = "completed" if session.ended_at_utc is not None else (
            "running" if session.started_at_utc is not None else "draft"
        )
        technical_event(
            _logger,
            logging.INFO,
            "session.saved",
            study_id=session.study_id,
            session_id=session.id,
            session_state=state,
            simulated=session.simulated,
        )


class SQLiteEventRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def append(self, study_id: UUID, event: Event) -> None:
        if event.study_id != study_id:
            raise ValueError("event.study_id does not match repository study_id")
        _ensure_mode(self.db, event.simulated)
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO events(id, study_id, session_id, category, occurred_at_utc, "
                "simulated, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(event.id),
                    str(event.study_id),
                    str(event.session_id),
                    event.category.value,
                    event.occurred_at_utc.isoformat(),
                    int(event.simulated),
                    _payload(event),
                ),
            )

    def list_for_study(self, study_id: UUID) -> Sequence[Event]:
        rows = self.db.fetchall(
            "SELECT payload_json FROM events WHERE study_id = ? "
            "ORDER BY occurred_at_utc, id",
            (str(study_id),),
        )
        return tuple(_decode(row["payload_json"], Event) for row in rows)

    def search(
        self,
        study_id: UUID,
        *,
        start_utc=None,
        end_utc=None,
        category: str | None = None,
        query: str | None = None,
    ) -> Sequence[Event]:
        clauses = ["study_id = ?"]
        parameters: list[Any] = [str(study_id)]
        if start_utc is not None:
            clauses.append("occurred_at_utc >= ?")
            parameters.append(start_utc.isoformat())
        if end_utc is not None:
            clauses.append("occurred_at_utc <= ?")
            parameters.append(end_utc.isoformat())
        if category is not None:
            clauses.append("category = ?")
            parameters.append(category)
        rows = self.db.fetchall(
            "SELECT payload_json FROM events WHERE " + " AND ".join(clauses) +
            " ORDER BY occurred_at_utc, id",
            parameters,
        )
        events = tuple(_decode(row["payload_json"], Event) for row in rows)
        normalized = (query or "").strip().casefold()
        if not normalized:
            return events
        return tuple(
            event for event in events
            if normalized in f"{event.event_type} {event.text} {event.author}".casefold()
        )


class SQLiteAlarmRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def save(self, alarm: Alarm) -> None:
        _ensure_mode(self.db, alarm.simulated)
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO alarms(id, study_id, session_id, status, severity, activated_at_utc, "
                "simulated, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, payload_json=excluded.payload_json",
                (
                    str(alarm.id),
                    str(alarm.study_id),
                    str(alarm.session_id),
                    alarm.status.value,
                    alarm.severity.value,
                    alarm.activated_at_utc.isoformat(),
                    int(alarm.simulated),
                    _payload(alarm),
                ),
            )


class SQLiteTrendRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def append(self, aggregate: TrendAggregate) -> None:
        _ensure_mode(self.db, aggregate.simulated)
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO trend_aggregates(id, study_id, session_id, interval_start_utc, "
                "interval_end_utc, position_seconds, aggregation_kind, quality, "
                "algorithm_version, simulated, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(aggregate.id), str(aggregate.study_id), str(aggregate.session_id),
                    aggregate.interval_start_utc.isoformat(), aggregate.interval_end_utc.isoformat(),
                    aggregate.position_seconds, aggregate.aggregation_kind,
                    aggregate.quality.value, aggregate.algorithm_version,
                    int(aggregate.simulated), _payload(aggregate),
                ),
            )

    def list_range(
        self,
        study_id: UUID,
        start_utc,
        end_utc,
        *,
        aggregation_kind: str = "interval",
    ) -> Sequence[TrendAggregate]:
        if end_utc < start_utc:
            return ()
        rows = self.db.fetchall(
            "SELECT payload_json FROM trend_aggregates WHERE study_id = ? "
            "AND aggregation_kind = ? AND interval_end_utc >= ? AND interval_start_utc <= ? "
            "ORDER BY interval_start_utc, id",
            (str(study_id), aggregation_kind, start_utc.isoformat(), end_utc.isoformat()),
        )
        return tuple(_decode(row["payload_json"], TrendAggregate) for row in rows)

    def bounds(self, study_id: UUID, *, aggregation_kind: str = "interval"):
        row = self.db.fetchone(
            "SELECT MIN(interval_start_utc) AS start, MAX(interval_end_utc) AS end "
            "FROM trend_aggregates WHERE study_id = ? AND aggregation_kind = ?",
            (str(study_id), aggregation_kind),
        )
        if row is None or row["start"] is None:
            return None
        from datetime import datetime
        return datetime.fromisoformat(row["start"]), datetime.fromisoformat(row["end"])


class SQLiteReportRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def get(self, report_id: UUID) -> Report | None:
        row = self.db.fetchone(
            "SELECT payload_json FROM reports WHERE id = ?", (str(report_id),)
        )
        return None if row is None else _decode(row["payload_json"], Report)

    def list_for_study(self, study_id: UUID) -> Sequence[Report]:
        rows = self.db.fetchall(
            "SELECT payload_json FROM reports WHERE study_id = ? "
            "ORDER BY created_at_utc, id",
            (str(study_id),),
        )
        return tuple(_decode(row["payload_json"], Report) for row in rows)

    def list_all(self) -> Sequence[Report]:
        rows = self.db.fetchall(
            "SELECT payload_json FROM reports ORDER BY created_at_utc DESC, id"
        )
        return tuple(_decode(row["payload_json"], Report) for row in rows)

    def save(self, report: Report) -> None:
        _ensure_mode(self.db, report.simulated)
        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO reports(id, study_id, status, created_at_utc, simulated, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                "status=excluded.status, payload_json=excluded.payload_json",
                (
                    str(report.id),
                    str(report.study_id),
                    report.status.value,
                    report.created_at_utc.isoformat(),
                    int(report.simulated),
                    _payload(report),
                ),
            )
        technical_event(
            _logger,
            logging.INFO,
            "report.saved",
            study_id=report.study_id,
            report_status=report.status.value,
            simulated=report.simulated,
        )


class SQLiteSettingsRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def load(self) -> Mapping[str, Any]:
        rows = self.db.fetchall(
            "SELECT key, value_json FROM settings ORDER BY key"
        )
        return {row["key"]: json.loads(row["value_json"]) for row in rows}

    def save(self, values: Mapping[str, Any]) -> None:
        encoded = {
            key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            for key, value in values.items()
        }
        with self.db.transaction() as connection:
            connection.executemany(
                "INSERT INTO settings(key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                encoded.items(),
            )


@dataclass(frozen=True, slots=True)
class RepositoryBundle:
    patients: SQLitePatientRepository
    studies: SQLiteStudyRepository
    sessions: SQLiteMonitoringSessionRepository
    events: SQLiteEventRepository
    trends: SQLiteTrendRepository
    alarms: SQLiteAlarmRepository
    reports: SQLiteReportRepository
    settings: SQLiteSettingsRepository

    @classmethod
    def build(cls, database: Database) -> "RepositoryBundle":
        return cls(
            patients=SQLitePatientRepository(database),
            studies=SQLiteStudyRepository(database),
            sessions=SQLiteMonitoringSessionRepository(database),
            events=SQLiteEventRepository(database),
            trends=SQLiteTrendRepository(database),
            alarms=SQLiteAlarmRepository(database),
            reports=SQLiteReportRepository(database),
            settings=SQLiteSettingsRepository(database),
        )
