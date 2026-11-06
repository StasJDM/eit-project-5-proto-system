"""Adapter for the external breathclf_identification 0.0.4 model format."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import os

import numpy as np

from .breathing_classification import (
    BreathingClass,
    BreathingClassificationResult,
    BreathingModelVisualization,
)


BREATHCLF_FORMAT_VERSION = 3
DEFAULT_MODEL_FILE = "newborn_mlp_tanh_20261103_112718.joblib"

_CLASS_MAP = {
    "апноэ обструктивное": BreathingClass.OBSTRUCTIVE_APNEA,
    "апноэ рефлекторное": BreathingClass.REFLEX_APNEA,
    "апноэ смешанное": BreathingClass.MIXED_APNEA,
    "апноэ центральное": BreathingClass.CENTRAL_APNEA,
    "брадипноэ": BreathingClass.BRADYPNEA,
    "гаспинг": BreathingClass.GASPING,
    "диспноэ": BreathingClass.DYSPNEA,
    "дыхание с рестрикцией": BreathingClass.RESTRICTIVE,
    "периодическое": BreathingClass.PERIODIC,
    "тахипноэ": BreathingClass.TACHYPNEA,
    "эупноэ": BreathingClass.EUPNEA,
}


@dataclass(slots=True)
class _LoadedBundle:
    model: Any
    projector: Any
    class_names: tuple[str, ...]
    n_timesteps: int
    sample_rate_hz: float
    method_key: str
    trained_at: str
    patient_type: str
    train_scores: np.ndarray
    train_labels: np.ndarray
    templates: np.ndarray


def default_breath_model_path() -> Path:
    configured = os.environ.get("EIT_BREATH_MODEL_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    project_root = Path(__file__).resolve().parents[2]
    packaged = project_root / "models" / "breathing" / DEFAULT_MODEL_FILE
    if packaged.is_file():
        return packaged
    return (
        project_root.parent
        / "breathclf_identification_0.0.4"
        / "models"
        / DEFAULT_MODEL_FILE
    )


class BreathClfClassifier:
    """Run a breathclf bundle against the latest synchronized global curve."""

    clinically_validated = False
    operational = True

    def __init__(self, model_path: Path | str | None = None) -> None:
        self.model_path = Path(model_path) if model_path else default_breath_model_path()
        self._bundle: _LoadedBundle | None = None
        self._load_error: str | None = None

    @property
    def algorithm_version(self) -> str:
        bundle = self._ensure_bundle()
        if bundle is None:
            return "breathclf-0.0.4-unavailable"
        stamp = bundle.trained_at.replace("-", "").replace(":", "").replace(" ", "T")
        return f"breathclf-0.0.4-{bundle.method_key}-{stamp}"

    @property
    def load_error(self) -> str | None:
        self._ensure_bundle()
        return self._load_error

    def classify(
        self,
        values: np.ndarray,
        sample_rate_hz: float,
        interval_start_utc: datetime,
        interval_end_utc: datetime,
    ) -> BreathingClassificationResult:
        bundle = self._ensure_bundle()
        if bundle is None:
            return self._undetermined(
                interval_start_utc,
                interval_end_utc,
                "breathclf_model_unavailable",
            )
        curve = self._prepare_curve(values, sample_rate_hz, bundle)
        if curve is None:
            return self._undetermined(
                interval_start_utc,
                interval_end_utc,
                "breathclf_insufficient_signal",
            )
        try:
            probabilities = np.asarray(bundle.model.predict_proba(curve[None, :]), dtype=float)
            column = int(np.argmax(probabilities[0]))
            raw_label = int(np.asarray(bundle.model.classes_)[column])
            class_name = bundle.class_names[raw_label]
            breathing_class = _CLASS_MAP[class_name.casefold().strip()]
            confidence = float(probabilities[0, column])
        except Exception:
            return self._undetermined(
                interval_start_utc,
                interval_end_utc,
                "breathclf_inference_failed",
            )
        duration = (bundle.n_timesteps - 1) / bundle.sample_rate_hz
        return BreathingClassificationResult(
            breathing_class=breathing_class,
            confidence=max(0.0, min(1.0, confidence)),
            interval_start_utc=max(
                interval_start_utc,
                interval_end_utc - timedelta(seconds=duration),
            ),
            interval_end_utc=interval_end_utc,
            algorithm_version=self.algorithm_version,
            reason="experimental_model_not_clinically_validated",
        )

    def visualization(
        self, values: np.ndarray, sample_rate_hz: float
    ) -> BreathingModelVisualization | None:
        bundle = self._ensure_bundle()
        if bundle is None:
            return None
        curve = self._prepare_curve(values, sample_rate_hz, bundle)
        current = None
        if curve is not None:
            try:
                current = np.asarray(bundle.projector.transform(curve[None, :])[0], dtype=float)
            except Exception:
                current = None
        explained = np.asarray(
            getattr(bundle.projector, "explained_variance_ratio_", ()), dtype=float
        )
        return BreathingModelVisualization(
            signature=self.algorithm_version,
            class_names=bundle.class_names,
            train_scores=bundle.train_scores.copy(),
            train_labels=bundle.train_labels.copy(),
            templates=bundle.templates.copy(),
            explained_variance_ratio=explained,
            sample_rate_hz=bundle.sample_rate_hz,
            current_score=current,
        )

    def _ensure_bundle(self) -> _LoadedBundle | None:
        if self._bundle is not None or self._load_error is not None:
            return self._bundle
        if not self.model_path.is_file():
            self._load_error = f"model file not found: {self.model_path}"
            return None
        try:
            import joblib

            payload = joblib.load(self.model_path)
            if not isinstance(payload, dict) or payload.get("format") != BREATHCLF_FORMAT_VERSION:
                raise ValueError("unsupported breathclf model format")
            metadata = payload.get("meta")
            if not isinstance(metadata, dict):
                raise ValueError("breathclf metadata is missing")
            names = tuple(str(value) for value in metadata["class_names"])
            if not names or any(name.casefold().strip() not in _CLASS_MAP for name in names):
                raise ValueError("breathclf model contains unsupported classes")
            n_timesteps = int(metadata["n_timesteps"])
            sample_rate = float(metadata["fs"])
            if n_timesteps < 2 or not np.isfinite(sample_rate) or sample_rate <= 0:
                raise ValueError("breathclf sampling metadata is invalid")
            projector = metadata["projector"]
            scores = np.asarray(metadata.get("train_scores", ()), dtype=float)
            labels = np.asarray(metadata.get("train_labels", ()), dtype=int)
            templates = np.asarray(metadata.get("templates", ()), dtype=float)
            self._bundle = _LoadedBundle(
                model=payload["model"],
                projector=projector,
                class_names=names,
                n_timesteps=n_timesteps,
                sample_rate_hz=sample_rate,
                method_key=str(metadata["method_key"]),
                trained_at=str(metadata["trained_at"]),
                patient_type=str(metadata["patient_type"]),
                train_scores=scores,
                train_labels=labels,
                templates=templates,
            )
        except Exception as error:
            self._load_error = f"{type(error).__name__}: {error}"
        return self._bundle

    @staticmethod
    def _prepare_curve(
        values: np.ndarray, sample_rate_hz: float, bundle: _LoadedBundle
    ) -> np.ndarray | None:
        signal = np.asarray(values, dtype=float).reshape(-1)
        if (
            not np.isfinite(sample_rate_hz)
            or sample_rate_hz <= 0
            or not np.all(np.isfinite(signal))
        ):
            return None
        duration = (bundle.n_timesteps - 1) / bundle.sample_rate_hz
        available_duration = (signal.size - 1) / sample_rate_hz if signal.size else 0.0
        if signal.size < 2 or available_duration + 1e-9 < duration:
            return None
        source_time = np.arange(signal.size, dtype=float) / sample_rate_hz
        target_end = source_time[-1]
        target_time = target_end - duration + np.arange(bundle.n_timesteps) / bundle.sample_rate_hz
        return np.interp(target_time, source_time, signal)

    def _undetermined(
        self, start: datetime, end: datetime, reason: str
    ) -> BreathingClassificationResult:
        return BreathingClassificationResult(
            BreathingClass.UNDETERMINED,
            0.0,
            start,
            end,
            self.algorithm_version,
            reason,
        )
