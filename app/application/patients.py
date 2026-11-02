"""Patient-card use cases shared by the Qt UI and automated tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
import sqlite3
from uuid import UUID, uuid4

from .ports import PatientRepository
from ..domain import Diagnosis, Patient, VentilationDetails, utc_now


EXTERNAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,31}$")
MEDICAL_RECORD_RE = re.compile(r"^[\w./-]{1,64}$", re.UNICODE)
NAME_RE = re.compile(r"^[^\d\W][^\d]{0,63}$", re.UNICODE)


class PatientValidationError(ValueError):
    def __init__(self, field_errors: dict[str, str]):
        self.field_errors = field_errors
        super().__init__("; ".join(field_errors.values()))


class DuplicatePatientError(PatientValidationError):
    pass


@dataclass(frozen=True, slots=True)
class PatientDraft:
    external_id: str = ""
    medical_record_number: str = ""
    family_name: str = ""
    given_name: str = ""
    middle_name: str = ""
    date_of_birth: date | None = None
    sex: str = ""
    weight_kg: float | None = None
    height_cm: float | None = None
    chest_circumference_cm: float | None = None
    main_diagnosis: Diagnosis | None = None
    accompanying_diagnoses: tuple[Diagnosis, ...] = ()
    ventilation: VentilationDetails = VentilationDetails()


def full_years(date_of_birth: date, on_date: date | None = None) -> int:
    today = on_date or date.today()
    if date_of_birth > today:
        raise ValueError("date of birth must not be in the future")
    return today.year - date_of_birth.year - (
        (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
    )


class PatientService:
    def __init__(self, repository: PatientRepository):
        self.repository = repository

    def assign_external_id(self) -> str:
        for _ in range(100):
            candidate = f"P-{uuid4().hex[:8].upper()}"
            if self.repository.find_by_external_id(candidate) is None:
                return candidate
        raise RuntimeError("could not allocate a unique patient ID")

    def search(self, query: str, *, limit: int = 50):
        return self.repository.search(query, limit=limit)

    def save(self, draft: PatientDraft, *, patient_id: UUID | None = None) -> Patient:
        errors = self.validate(draft, patient_id=patient_id)
        if errors:
            duplicate_fields = {"external_id", "medical_record_number"} & errors.keys()
            error_type = DuplicatePatientError if duplicate_fields else PatientValidationError
            raise error_type(errors)

        existing = self.repository.get(patient_id) if patient_id is not None else None
        now = utc_now()
        patient = Patient(
            id=patient_id or uuid4(),
            external_id=_optional_text(draft.external_id.upper()),
            medical_record_number=_optional_text(draft.medical_record_number),
            family_name=_optional_text(draft.family_name),
            given_name=_optional_text(draft.given_name),
            middle_name=_optional_text(draft.middle_name),
            date_of_birth=draft.date_of_birth,
            sex=_optional_text(draft.sex),
            weight_kg=draft.weight_kg,
            height_cm=draft.height_cm,
            chest_circumference_cm=draft.chest_circumference_cm,
            main_diagnosis=draft.main_diagnosis,
            accompanying_diagnoses=draft.accompanying_diagnoses,
            ventilation=draft.ventilation,
            created_at_utc=existing.created_at_utc if existing else now,
            updated_at_utc=now,
        )
        try:
            self.repository.save(patient)
        except sqlite3.IntegrityError as exc:
            raise DuplicatePatientError(
                {"patient": "A patient with this ID or medical record number already exists"}
            ) from exc
        return patient

    def validate(self, draft: PatientDraft, *, patient_id: UUID | None = None) -> dict[str, str]:
        errors: dict[str, str] = {}
        for field_name, value in (
            ("family_name", draft.family_name),
            ("given_name", draft.given_name),
        ):
            if not value.strip():
                errors[field_name] = "Last name and first name are required"
            elif not NAME_RE.fullmatch(value.strip()):
                errors[field_name] = "Name contains invalid characters"
        if draft.middle_name.strip() and not NAME_RE.fullmatch(draft.middle_name.strip()):
            errors["middle_name"] = "Middle name contains invalid characters"
        if draft.date_of_birth is None:
            errors["date_of_birth"] = "Date of birth is required"
        else:
            try:
                full_years(draft.date_of_birth)
            except ValueError:
                errors["date_of_birth"] = "Date of birth must not be in the future"
        if draft.sex not in {"male", "female"}:
            errors["sex"] = "Sex is required"
        self._validate_range(errors, "weight_kg", draft.weight_kg, 0.5, 500.0)
        self._validate_range(errors, "height_cm", draft.height_cm, 20.0, 250.0)
        self._validate_range(
            errors, "chest_circumference_cm", draft.chest_circumference_cm, 20.0, 250.0
        )
        external_id = draft.external_id.strip()
        if not external_id or not EXTERNAL_ID_RE.fullmatch(external_id):
            errors["external_id"] = "ID must contain 3-32 Latin letters, digits, '.', '_' or '-'"
        else:
            duplicate = self.repository.find_by_external_id(external_id)
            if duplicate is not None and duplicate.id != patient_id:
                errors["external_id"] = "Patient ID already exists"
        record = draft.medical_record_number.strip()
        if not record or not MEDICAL_RECORD_RE.fullmatch(record):
            errors["medical_record_number"] = "Medical record number is required and has invalid format"
        else:
            duplicate = self.repository.find_by_medical_record_number(record)
            if duplicate is not None and duplicate.id != patient_id:
                errors["medical_record_number"] = "Medical record number already exists"
        if draft.ventilation.enabled:
            if not draft.ventilation.mode:
                errors["ventilation.mode"] = "Ventilation mode is required"
            if draft.ventilation.fio2_percent is None:
                errors["ventilation.fio2_percent"] = "FiO2 is required"
            if draft.ventilation.peep_cmh2o is None:
                errors["ventilation.peep_cmh2o"] = "PEEP is required"
        return errors

    @staticmethod
    def _validate_range(
        errors: dict[str, str], field_name: str, value: float | None,
        minimum: float, maximum: float,
    ) -> None:
        if value is None or not minimum <= value <= maximum:
            errors[field_name] = f"Value must be between {minimum:g} and {maximum:g}"


def _optional_text(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None
