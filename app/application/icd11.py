"""Offline bilingual ICD-10/ICD-11 lookup for the patient card."""

from __future__ import annotations

import csv
import gzip
from pathlib import Path

from .events import ApplicationEvent, EventBus, EventType
from .ports import SettingsRepository
from ..domain import Diagnosis


DEFAULT_DIAGNOSIS_CLASSIFICATION = "ICD-10"
SUPPORTED_DIAGNOSIS_CLASSIFICATIONS = ("ICD-10", "ICD-11")
DIAGNOSIS_CLASSIFICATION_SETTING = "diagnosis_classification"

ICD10_RELEASE = "WHO 2019 / RU 2026 export"
ICD10_SOURCE_URL = "https://icdcdn.who.int/icd10/index.html"
ICD11_RELEASE = "2026-01"
ICD11_SOURCE_URL = "https://icd.who.int/browse/2026-01/mms/en"

_CATALOGUE_PATH = (
    Path(__file__).resolve().parent.parent / "resources" / "icd_diagnoses_ru_en.tsv.gz"
)


def _load_catalogues() -> dict[str, tuple[Diagnosis, ...]]:
    grouped: dict[str, list[Diagnosis]] = {
        classification: [] for classification in SUPPORTED_DIAGNOSIS_CLASSIFICATIONS
    }
    with gzip.open(_CATALOGUE_PATH, "rt", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            classification = row["classification"]
            title_en = row["title_en"].strip()
            title_ru = row["title_ru"].strip()
            canonical_title = title_en or title_ru
            if not canonical_title:
                continue
            grouped[classification].append(Diagnosis(
                code=row["code"].strip(),
                title=canonical_title,
                classification=classification,
                title_ru=title_ru or None,
            ))
    return {key: tuple(values) for key, values in grouped.items()}


DIAGNOSIS_CATALOGUES = _load_catalogues()
ICD10_CATALOGUE = DIAGNOSIS_CATALOGUES["ICD-10"]
ICD11_CATALOGUE = DIAGNOSIS_CATALOGUES["ICD-11"]
_DIAGNOSIS_BY_CODE = {
    classification: {item.code.casefold(): item for item in catalogue}
    for classification, catalogue in DIAGNOSIS_CATALOGUES.items()
}


def diagnosis_title(diagnosis: Diagnosis, language: str) -> str:
    """Return the requested localized title, falling back to the available one."""
    if language == "ru" and diagnosis.title_ru:
        return diagnosis.title_ru
    return diagnosis.title


def diagnosis_text(diagnosis: Diagnosis, language: str) -> str:
    return f"{diagnosis.code} — {diagnosis_title(diagnosis, language)}"


def search_diagnoses(
    query: str,
    classification: str = DEFAULT_DIAGNOSIS_CLASSIFICATION,
    *,
    limit: int = 50,
) -> tuple[Diagnosis, ...]:
    catalogue = _catalogue(classification)
    normalized = " ".join(query.casefold().split())
    result: list[Diagnosis] = []
    for item in catalogue:
        searchable = f"{item.code} {item.title} {item.title_ru or ''}".casefold()
        if normalized and normalized not in searchable:
            continue
        result.append(item)
        if len(result) >= limit:
            break
    return tuple(result)


def resolve_diagnosis(
    text: str, classification: str = DEFAULT_DIAGNOSIS_CLASSIFICATION
) -> Diagnosis | None:
    normalized = text.strip().casefold()
    if not normalized:
        return None
    try:
        direct = _DIAGNOSIS_BY_CODE[classification].get(normalized)
    except KeyError as exc:
        raise ValueError(f"unsupported diagnosis classification: {classification}") from exc
    if direct is not None:
        return direct
    for item in _catalogue(classification):
        accepted = {
            diagnosis_text(item, "en").casefold(),
            diagnosis_text(item, "ru").casefold(),
        }
        if normalized in accepted:
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
