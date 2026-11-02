from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from app.application import (
    BreathingClass, BreathingClassificationResult, BreathingClassificationService,
    LabeledBreathingSample,
)


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


if __name__ == "__main__":
    unittest.main()
