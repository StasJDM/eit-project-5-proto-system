"""PII-safe structured technical logging with bounded file rotation."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
from typing import Any, Iterator
from uuid import UUID

from .config import AppConfig


logging.getLogger("eit").addHandler(logging.NullHandler())

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_study_id: ContextVar[str | None] = ContextVar("study_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)

_EVENT_CODE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_ALLOWED_DETAILS = frozenset(
    {
        "operation",
        "state",
        "mode",
        "source_type",
        "schema_version",
        "sequence_number",
        "quality",
        "simulated",
        "result",
        "error_type",
        "export_format",
        "session_state",
        "study_status",
        "report_status",
        "frame_count",
    }
)


class StructuredJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event_code = getattr(record, "event_code", "unstructured_log_ignored")
        document: dict[str, Any] = {
            "timestamp_utc": datetime.fromtimestamp(
                record.created, timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "event": event_code,
        }
        for key in ("correlation_id", "study_id", "session_id"):
            value = getattr(record, key, None)
            if value is not None:
                document[key] = value
        details = getattr(record, "safe_details", None)
        if details:
            document["details"] = details
        return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "correlation_id", None) is None:
            record.correlation_id = _correlation_id.get()
        if getattr(record, "study_id", None) is None:
            record.study_id = _study_id.get()
        if getattr(record, "session_id", None) is None:
            record.session_id = _session_id.get()
        return True


def configure_logging(config: AppConfig) -> Path:
    """Configure the ``eit`` logger and return the active log path."""
    path = config.log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("eit")
    logger.setLevel(getattr(logging, config.log_level))
    logger.propagate = False
    for handler in tuple(logger.handlers):
        if getattr(handler, "_eit_managed", False):
            logger.removeHandler(handler)
            handler.close()
    handler = RotatingFileHandler(
        path,
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
        encoding="utf-8",
    )
    handler._eit_managed = True
    handler.setLevel(getattr(logging, config.log_level))
    handler.setFormatter(StructuredJsonFormatter())
    handler.addFilter(CorrelationFilter())
    logger.addHandler(handler)
    return path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"eit.{name}")


def technical_event(
    logger: logging.Logger,
    level: int,
    event_code: str,
    *,
    study_id: UUID | str | None = None,
    session_id: UUID | str | None = None,
    correlation_id: UUID | str | None = None,
    **details: Any,
) -> None:
    """Write one event while rejecting fields that may contain domain data."""
    if not _EVENT_CODE.fullmatch(event_code):
        raise ValueError("event_code must contain only lowercase technical tokens")
    forbidden = set(details) - _ALLOWED_DETAILS
    if forbidden:
        raise ValueError(
            "unsafe technical log fields: " + ", ".join(sorted(forbidden))
        )
    normalized = {key: _safe_scalar(value, key) for key, value in details.items()}
    study = str(study_id) if study_id is not None else _study_id.get()
    session = str(session_id) if session_id is not None else _session_id.get()
    correlation = (
        str(correlation_id)
        if correlation_id is not None
        else _correlation_id.get() or session or study
    )
    logger.log(
        level,
        event_code,
        extra={
            "event_code": event_code,
            "safe_details": normalized,
            "study_id": study,
            "session_id": session,
            "correlation_id": correlation,
        },
    )


@contextmanager
def log_context(
    *,
    study_id: UUID | str | None = None,
    session_id: UUID | str | None = None,
    correlation_id: UUID | str | None = None,
) -> Iterator[None]:
    study = str(study_id) if study_id is not None else None
    session = str(session_id) if session_id is not None else None
    correlation = str(correlation_id) if correlation_id is not None else session or study
    tokens = (
        (_study_id, _study_id.set(study)),
        (_session_id, _session_id.set(session)),
        (_correlation_id, _correlation_id.set(correlation)),
    )
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


def _safe_scalar(value: Any, key: str) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (UUID,)):
        return str(value)
    raise ValueError(f"unsafe value type for technical log field {key}: {type(value).__name__}")
