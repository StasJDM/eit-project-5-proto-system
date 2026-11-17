from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

import numpy as np

from app.application import (
    BreathClfClassifier, BreathingClass, BreathingClassificationResult,
    BreathingClassificationService,
    LabeledBreathingSample,
    SpectralBreathingClassifier,
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

    def test_spectral_classifier_recognizes_stable_rate_classes(self):
        classifier = SpectralBreathingClassifier()
        for rate, expected in (
            (8.0, BreathingClass.BRADYPNEA),
            (15.0, BreathingClass.EUPNEA),
            (40.0, BreathingClass.TACHYPNEA),
        ):
            with self.subTest(rate=rate):
                fs = 25.0
                time = np.arange(0.0, 60.0, 1.0 / fs)
                values = np.sin(2.0 * np.pi * rate / 60.0 * time)
                result = classifier.classify(values, fs, NOW, NOW + timedelta(seconds=60))
                self.assertIs(result.breathing_class, expected)
                self.assertGreater(result.confidence, 0.5)

    def test_spectral_classifier_detects_periodic_modulation_and_apnea(self):
        classifier = SpectralBreathingClassifier()
        fs = 25.0
        time = np.arange(0.0, 60.0, 1.0 / fs)
        carrier = np.sin(2.0 * np.pi * 15.0 / 60.0 * time)

        periodic = carrier * (0.55 + 0.45 * np.sin(2.0 * np.pi * time / 30.0))
        periodic_result = classifier.classify(
            periodic, fs, NOW, NOW + timedelta(seconds=60)
        )
        self.assertIs(periodic_result.breathing_class, BreathingClass.PERIODIC)

        apnea = carrier.copy()
        apnea[time >= 47.0] = 0.0
        apnea_result = classifier.classify(apnea, fs, NOW, NOW + timedelta(seconds=60))
        self.assertIs(apnea_result.breathing_class, BreathingClass.APNEA)

    def test_spectral_classifier_rejects_short_or_flat_signal(self):
        classifier = SpectralBreathingClassifier()
        short = classifier.classify(
            np.ones(100), 25.0, NOW, NOW + timedelta(seconds=4)
        )
        flat = classifier.classify(
            np.ones(1500), 25.0, NOW, NOW + timedelta(seconds=60)
        )
        self.assertIs(short.breathing_class, BreathingClass.UNDETERMINED)
        self.assertEqual(short.reason, "spectral_insufficient_signal")
        self.assertIs(flat.breathing_class, BreathingClass.UNDETERMINED)
        self.assertEqual(flat.reason, "spectral_low_energy")

    def test_spectral_classifier_detects_gasping_and_irregular_breathing(self):
        classifier = SpectralBreathingClassifier()
        fs = 25.0
        time = np.arange(0.0, 60.0, 1.0 / fs)

        gasping = np.zeros_like(time)
        for center in (5.0, 15.0, 25.0, 35.0, 45.0, 55.0):
            gasping += np.exp(-0.5 * ((time - center) / 0.35) ** 2)
        gasping_result = classifier.classify(
            gasping, fs, NOW, NOW + timedelta(seconds=60)
        )
        self.assertIs(gasping_result.breathing_class, BreathingClass.GASPING)

        segments = []
        segment_time = np.arange(0.0, 10.0, 1.0 / fs)
        for rate in (12.0, 24.0, 16.0, 28.0, 14.0, 22.0):
            segments.append(np.sin(2.0 * np.pi * rate / 60.0 * segment_time))
        irregular = np.concatenate(segments)
        dyspnea_result = classifier.classify(
            irregular, fs, NOW, NOW + timedelta(seconds=60)
        )
        self.assertIs(dyspnea_result.breathing_class, BreathingClass.DYSPNEA)


if __name__ == "__main__":
    unittest.main()
