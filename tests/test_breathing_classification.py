from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

import numpy as np

from app.application import (
    BreathClfClassifier, BreathingClass, BreathingClassificationResult,
    BreathingClassificationService,
    LabeledBreathingSample,
)
from app.application.breathclf_adapter import _LoadedBundle


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _ValidatedClassifier:
    algorithm_version = "independent-test-classifier-1"
    clinically_validated = True

    def classify(self, values, sample_rate_hz, interval_start_utc, interval_end_utc):
        label = BreathingClass.EUPNEA if values.mean() >= 0 else BreathingClass.APNEA
        return BreathingClassificationResult(
            label, 0.9, interval_start_utc, interval_end_utc,
            self.algorithm_version,
        )


class _FakeBreathModel:
    classes_ = np.arange(11)

    def predict_proba(self, values):
        result = np.zeros((len(values), 11), dtype=float)
        result[:, 10] = 0.92
        result[:, 9] = 0.08
        return result


class _FakeProjector:
    n_components_ = 3
    explained_variance_ratio_ = np.asarray([0.6, 0.25, 0.1])

    def transform(self, values):
        values = np.asarray(values, dtype=float)
        return np.column_stack((values.mean(1), values.std(1), values[:, -1]))


class BreathingClassificationTest(unittest.TestCase):
    def test_unconfigured_model_is_undetermined_not_rr_heuristic(self):
        result = BreathingClassificationService().classify(
            [1.0] * 100, 25.0, NOW, NOW + timedelta(seconds=4)
        )
        self.assertIs(result.breathing_class, BreathingClass.UNDETERMINED)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.reason, "validated_classifier_not_configured")

    def test_manual_assessment_is_separate_from_automatic_result(self):
        service = BreathingClassificationService()
        manual = service.set_manual_assessment(BreathingClass.PERIODIC, "doctor")
        automatic = service.classify([1.0], 25.0, NOW, NOW)
        self.assertIs(manual.breathing_class, BreathingClass.PERIODIC)
        self.assertIs(automatic.breathing_class, BreathingClass.UNDETERMINED)

    def test_validation_metrics_use_labeled_samples(self):
        service = BreathingClassificationService(_ValidatedClassifier())
        samples = (
            LabeledBreathingSample((1.0, 2.0), 25.0, BreathingClass.EUPNEA, NOW, NOW),
            LabeledBreathingSample((-1.0, -2.0), 25.0, BreathingClass.APNEA, NOW, NOW),
        )
        metrics = service.validate(samples)
        self.assertEqual(metrics.sample_count, 2)
        self.assertEqual(metrics.accuracy, 1.0)

    def test_breathclf_adapter_resamples_live_curve_and_marks_result_experimental(self):
        class_names = (
            "Апноэ обструктивное", "Апноэ рефлекторное", "Апноэ смешанное",
            "Апноэ центральное", "Брадипноэ", "Гаспинг", "Диспноэ",
            "Дыхание с рестрикцией", "Периодическое", "Тахипноэ", "Эупноэ",
        )
        classifier = BreathClfClassifier("/unused/fake.joblib")
        classifier._bundle = _LoadedBundle(
            model=_FakeBreathModel(),
            projector=_FakeProjector(),
            class_names=class_names,
            n_timesteps=600,
            sample_rate_hz=10.0,
            method_key="fake",
            trained_at="2026-11-03 11:27:18",
            patient_type="newborn",
            train_scores=np.zeros((11, 3)),
            train_labels=np.arange(11),
            templates=np.zeros((11, 600)),
        )
        service = BreathingClassificationService(
            classifier, allow_experimental=True
        )
        values = np.sin(np.linspace(0.0, 12.0 * np.pi, 1500))

        result = service.classify(
            values, 25.0, NOW, NOW + timedelta(seconds=60)
        )
        visualization = service.visualization(values, 25.0)

        self.assertIs(result.breathing_class, BreathingClass.EUPNEA)
        self.assertAlmostEqual(result.confidence, 0.92)
        self.assertEqual(result.reason, "experimental_model_not_clinically_validated")
        self.assertIsNotNone(visualization)
        self.assertEqual(visualization.current_score.shape, (3,))

    def test_breathclf_adapter_requires_full_model_window(self):
        classifier = BreathClfClassifier("/missing/model.joblib")
        result = BreathingClassificationService(
            classifier, allow_experimental=True
        ).classify([1.0] * 100, 25.0, NOW, NOW + timedelta(seconds=4))

        self.assertIs(result.breathing_class, BreathingClass.UNDETERMINED)
        self.assertEqual(result.reason, "breathclf_model_unavailable")


if __name__ == "__main__":
    unittest.main()
