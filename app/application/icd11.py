"""Offline ICD-10/ICD-11 lookup used by the prototype patient card.

The catalogue interface is deliberately independent from Qt and can later be
backed by an officially licensed complete release without changing the screen.
"""

from __future__ import annotations

from .events import ApplicationEvent, EventBus, EventType
from .ports import SettingsRepository
from ..domain import Diagnosis


DEFAULT_DIAGNOSIS_CLASSIFICATION = "ICD-10"
SUPPORTED_DIAGNOSIS_CLASSIFICATIONS = ("ICD-10", "ICD-11")
DIAGNOSIS_CLASSIFICATION_SETTING = "diagnosis_classification"

ICD10_RELEASE = "2019"
ICD10_SOURCE_URL = "https://icd.who.int/browse10/2019/en"
ICD11_RELEASE = "2026-01"
ICD11_SOURCE_URL = "https://icd.who.int/browse/2026-01/mms/en"

ICD10_CATALOGUE: tuple[Diagnosis, ...] = (
    Diagnosis("J18.9", "Pneumonia, unspecified organism", "ICD-10"),
    Diagnosis("J44.9", "Chronic obstructive pulmonary disease, unspecified", "ICD-10"),
    Diagnosis("J45.9", "Asthma, unspecified", "ICD-10"),
    Diagnosis("J80", "Adult respiratory distress syndrome", "ICD-10"),
    Diagnosis("J81", "Pulmonary oedema", "ICD-10"),
    Diagnosis("J96.9", "Respiratory failure, unspecified", "ICD-10"),
    Diagnosis("J90", "Pleural effusion, not elsewhere classified", "ICD-10"),
    Diagnosis("J93.9", "Pneumothorax, unspecified", "ICD-10"),
    Diagnosis("I10", "Essential (primary) hypertension", "ICD-10"),
    Diagnosis("I21.9", "Acute myocardial infarction, unspecified", "ICD-10"),
    Diagnosis("I50.9", "Heart failure, unspecified", "ICD-10"),
    Diagnosis("A41.9", "Sepsis, unspecified organism", "ICD-10"),
    Diagnosis("R57.2", "Septic shock", "ICD-10"),
)

ICD11_CATALOGUE: tuple[Diagnosis, ...] = (
    Diagnosis("CA40", "Pneumonia", "ICD-11"),
    Diagnosis("CA22", "Chronic obstructive pulmonary disease", "ICD-11"),
    Diagnosis("CA23", "Asthma", "ICD-11"),
    Diagnosis("CB00", "Acute respiratory distress syndrome", "ICD-11"),
    Diagnosis("CB01", "Pulmonary oedema", "ICD-11"),
    Diagnosis("CB41", "Respiratory failure", "ICD-11"),
    Diagnosis("CB27", "Pleural effusion", "ICD-11"),
    Diagnosis("CB21", "Pneumothorax", "ICD-11"),
    Diagnosis("BA00", "Essential hypertension", "ICD-11"),
    Diagnosis("BA41", "Acute myocardial infarction", "ICD-11"),
    Diagnosis("BD10", "Congestive heart failure", "ICD-11"),
    Diagnosis("1G40", "Sepsis without septic shock", "ICD-11"),
    Diagnosis("1G41", "Sepsis with septic shock", "ICD-11"),
)


DIAGNOSIS_CATALOGUES = {
    "ICD-10": ICD10_CATALOGUE,
    "ICD-11": ICD11_CATALOGUE,
}


def search_diagnoses(
    query: str,
    classification: str = DEFAULT_DIAGNOSIS_CLASSIFICATION,
    *,
    limit: int = 50,
) -> tuple[Diagnosis, ...]:
    catalogue = _catalogue(classification)
    normalized = " ".join(query.casefold().split())
    matches = (
        item for item in catalogue
        if not normalized or normalized in f"{item.code} {item.title}".casefold()
    )
    result: list[Diagnosis] = []
    for item in matches:
        result.append(item)
        if len(result) >= limit:
            break
    return tuple(result)


def resolve_diagnosis(
    text: str, classification: str = DEFAULT_DIAGNOSIS_CLASSIFICATION
) -> Diagnosis | None:
    catalogue = _catalogue(classification)
    normalized = text.strip().casefold()
    if not normalized:
        return None
    for item in catalogue:
        if normalized in {item.code.casefold(), f"{item.code} — {item.title}".casefold()}:
            return item
    return None


def search_icd11(query: str, *, limit: int = 50) -> tuple[Diagnosis, ...]:
    return search_diagnoses(query, "ICD-11", limit=limit)


def resolve_icd11(text: str) -> Diagnosis | None:
    return resolve_diagnosis(text, "ICD-11")


def _catalogue(classification: str) -> tuple[Diagnosis, ...]:
    try:
        return DIAGNOSIS_CATALOGUES[classification]
    except KeyError as exc:
        raise ValueError(f"unsupported diagnosis classification: {classification}") from exc


class DiagnosisCatalogService:
    """Persists and broadcasts the active diagnosis classification."""

    def __init__(self, settings: SettingsRepository, event_bus: EventBus):
        self._settings = settings
        self._event_bus = event_bus
        stored = settings.load().get(
            DIAGNOSIS_CLASSIFICATION_SETTING, DEFAULT_DIAGNOSIS_CLASSIFICATION
        )
        self._classification = (
            stored if stored in SUPPORTED_DIAGNOSIS_CLASSIFICATIONS
            else DEFAULT_DIAGNOSIS_CLASSIFICATION
        )

    @property
    def classification(self) -> str:
        return self._classification

    def set_classification(self, classification: str) -> None:
        _catalogue(classification)
        self._settings.save({DIAGNOSIS_CLASSIFICATION_SETTING: classification})
        if classification == self._classification:
            return
        self._classification = classification
        self._event_bus.publish(ApplicationEvent(
            EventType.SETTINGS_CHANGED,
            payload={DIAGNOSIS_CLASSIFICATION_SETTING: classification},
        ))

    def search(self, query: str, *, limit: int = 50) -> tuple[Diagnosis, ...]:
        return search_diagnoses(query, self._classification, limit=limit)

    def resolve(self, text: str) -> Diagnosis | None:
        return resolve_diagnosis(text, self._classification)
