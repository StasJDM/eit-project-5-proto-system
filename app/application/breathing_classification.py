"""Safety boundary for breathing-pattern classification.

No clinically validated classifier is bundled. The service therefore returns
``undetermined`` until an explicitly validated implementation is injected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, Sequence

import numpy as np

from ..domain import utc_now


class BreathingClass(str, Enum):
    UNDETERMINED = "undetermined"
    EUPNEA = "eupnea"
    TACHYPNEA = "tachypnea"
    BRADYPNEA = "bradypnea"
    APNEA = "apnea"
    PERIODIC = "periodic"
    RESTRICTIVE = "restrictive"
    RETRACTIVE = "retractive"
    GASPING = "gasping"
    DYSPNEA = "dyspnea"
    CENTRAL_APNEA = "central_apnea"
    OBSTRUCTIVE_APNEA = "obstructive_apnea"
    MIXED_APNEA = "mixed_apnea"
    REFLEX_APNEA = "reflex_apnea"


@dataclass(frozen=True, slots=True)
class BreathingClassificationResult:
    breathing_class: BreathingClass
    confidence: float
    interval_start_utc: datetime
    interval_end_utc: datetime
    algorithm_version: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ManualBreathingAssessment:
    breathing_class: BreathingClass
    author: str
    created_at_utc: datetime
    note: str | None = None


@dataclass(frozen=True, slots=True)
class LabeledBreathingSample:
    values: tuple[float, ...]
    sample_rate_hz: float
    expected: BreathingClass
    interval_start_utc: datetime
    interval_end_utc: datetime


@dataclass(frozen=True, slots=True)
class ClassificationMetrics:
    sample_count: int
    accuracy: float
    correct: int


class ValidatedBreathingClassifier(Protocol):
    algorithm_version: str
    clinically_validated: bool

    def classify(
        self, values: np.ndarray, sample_rate_hz: float,
        interval_start_utc: datetime, interval_end_utc: datetime,
    ) -> BreathingClassificationResult: ...


class BreathingClassificationService:
    def __init__(self, classifier: ValidatedBreathingClassifier | None = None) -> None:
        self._classifier = classifier
        self._manual: ManualBreathingAssessment | None = None

    @property
    def manual_assessment(self) -> ManualBreathingAssessment | None:
        return self._manual

    def classify(
        self,
        values: Sequence[float],
        sample_rate_hz: float,
        interval_start_utc: datetime,
        interval_end_utc: datetime,
    ) -> BreathingClassificationResult:
        if interval_start_utc.tzinfo is None or interval_end_utc.tzinfo is None:
            raise ValueError("classification interval must be timezone-aware")
        if interval_end_utc < interval_start_utc:
            raise ValueError("classification interval is reversed")
        classifier = self._classifier
        if classifier is None or not classifier.clinically_validated:
            return BreathingClassificationResult(
                BreathingClass.UNDETERMINED,
                0.0,
                interval_start_utc,
                interval_end_utc,
                "unvalidated-no-model-1.0.0",
                "validated_classifier_not_configured",
            )
        result = classifier.classify(
            np.asarray(values, dtype=float), float(sample_rate_hz),
            interval_start_utc, interval_end_utc,
        )
        if not 0.0 <= result.confidence <= 1.0:
            raise ValueError("classifier confidence must be between 0 and 1")
        return result

    def set_manual_assessment(
        self, breathing_class: BreathingClass, author: str, note: str | None = None,
        *, created_at_utc: datetime | None = None,
    ) -> ManualBreathingAssessment:
        if breathing_class is BreathingClass.UNDETERMINED:
            raise ValueError("manual assessment must select a breathing class")
        if not author.strip():
            raise ValueError("manual assessment author must not be blank")
        assessment = ManualBreathingAssessment(
            breathing_class, author.strip(), created_at_utc or utc_now(),
            note.strip() if note and note.strip() else None,
        )
        self._manual = assessment
        return assessment

    def validate(self, samples: Sequence[LabeledBreathingSample]) -> ClassificationMetrics:
        if not samples:
            raise ValueError("independent labeled test samples are required")
        correct = 0
        for sample in samples:
            result = self.classify(
                sample.values, sample.sample_rate_hz,
                sample.interval_start_utc, sample.interval_end_utc,
            )
            correct += int(result.breathing_class is sample.expected)
        return ClassificationMetrics(len(samples), correct / len(samples), correct)
