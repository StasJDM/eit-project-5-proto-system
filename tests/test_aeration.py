import unittest
from datetime import datetime, timezone

import numpy as np

from app.application import (
    ALGORITHM_VERSION,
    AerationAlgorithmParameters,
    AerationProcessor,
    calculate_aeration_metrics,
)
from app.domain import DataQuality, EITFrame


NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def frame(sequence: int, value: float, *, quality=DataQuality.VALID) -> EITFrame:
    return EITFrame(
        sequence_number=sequence,
        timestamp_utc=NOW,
        belt_index=0,
        global_impedance=value,
        roi_impedance=tuple(value * weight for weight in (4, 3, 2, 1, 4, 3, 2, 1)),
        reconstructed_delta_z=((value, value), (value, value)),
        quality=quality,
        simulated=True,
    )


class AerationCalculationTest(unittest.TestCase):
    def test_reference_signal_produces_expected_rr_tiv_and_regional_shares(self):
        fs = 25.0
        time = np.arange(0.0, 20.0, 1.0 / fs)
        breathing = 10.0 + 2.0 * np.sin(2.0 * np.pi * 0.25 * time)
        weights = np.asarray((4, 3, 2, 1, 4, 3, 2, 1), dtype=float)
        rois = [breathing * weight / weights.sum() for weight in weights]

        result = calculate_aeration_metrics(
            breathing,
            rois,
            AerationAlgorithmParameters(sample_rate_hz=fs),
        )

        self.assertEqual(result.algorithm_version, ALGORITHM_VERSION)
        self.assertEqual(result.quality, DataQuality.VALID)
        self.assertAlmostEqual(result.respiratory_rate_bpm, 15.0, places=6)
        self.assertAlmostEqual(result.tvi_au, 4.0, places=6)
        self.assertAlmostEqual(sum(result.roi_tvi_au), 4.0, places=6)
        self.assertAlmostEqual(result.right_percent, 50.0, places=6)
        self.assertAlmostEqual(result.left_percent, 50.0, places=6)
        self.assertAlmostEqual(result.right_left_ratio, 1.0, places=6)
        self.assertAlmostEqual(result.ventral_dorsal_ratio, 7.0 / 3.0, places=6)
        self.assertEqual(
            tuple(round(value, 6) for value in result.roi_percent),
            (20.0, 15.0, 10.0, 5.0, 20.0, 15.0, 10.0, 5.0),
        )

    def test_insufficient_and_flat_signals_are_explicitly_unavailable(self):
        params = AerationAlgorithmParameters(sample_rate_hz=25.0)
        short = np.ones(10)
        result = calculate_aeration_metrics(short, [short] * 8, params)
        self.assertEqual(result.quality, DataQuality.UNAVAILABLE)
        self.assertEqual(result.quality_reason, "insufficient_data")

        flat = np.ones(100)
        result = calculate_aeration_metrics(flat, [flat] * 8, params)
        self.assertEqual(result.quality, DataQuality.UNAVAILABLE)
        self.assertEqual(result.quality_reason, "no_detectable_breathing")
        self.assertEqual(result.status_for("rr").quality, DataQuality.UNAVAILABLE)
        self.assertEqual(result.status_for("tvi").quality, DataQuality.UNAVAILABLE)

    def test_time_fallback_keeps_amplitudes_but_not_a_false_rr(self):
        fs = 25.0
        time = np.arange(0.0, 3.0, 1.0 / fs)
        breathing = 2.0 + np.sin(2.0 * np.pi * 0.25 * time)
        rois = [breathing * weight / 20.0 for weight in (4, 3, 2, 1, 4, 3, 2, 1)]

        result = calculate_aeration_metrics(
            breathing,
            rois,
            AerationAlgorithmParameters(sample_rate_hz=fs),
        )

        self.assertIsNone(result.respiratory_rate_bpm)
        self.assertIsNotNone(result.tvi_au)
        self.assertEqual(result.quality, DataQuality.DEGRADED)
        self.assertEqual(result.status_for("rr").quality, DataQuality.UNAVAILABLE)
        self.assertEqual(
            result.status_for("rr").reason, "insufficient_complete_cycles"
        )
        self.assertEqual(result.status_for("tvi").quality, DataQuality.DEGRADED)

    def test_degraded_source_marks_each_available_metric_degraded(self):
        fs = 25.0
        time = np.arange(0.0, 20.0, 1.0 / fs)
        breathing = 5.0 + np.sin(2.0 * np.pi * 0.25 * time)
        rois = [breathing * weight / 20.0 for weight in (4, 3, 2, 1, 4, 3, 2, 1)]

        result = calculate_aeration_metrics(
            breathing,
            rois,
            AerationAlgorithmParameters(sample_rate_hz=fs),
            source_quality=DataQuality.DEGRADED,
            source_reason="source_quality_degraded",
        )

        self.assertEqual(result.quality, DataQuality.DEGRADED)
        for metric in ("rr", "tvi", "eeli", "eili", "r_pct", "roi_1"):
            self.assertEqual(result.status_for(metric).quality, DataQuality.DEGRADED)
            self.assertEqual(
                result.status_for(metric).reason, "source_quality_degraded"
            )

    def test_processor_filters_and_rejects_a_large_artifact(self):
        processor = AerationProcessor(
            AerationAlgorithmParameters(smoothing_samples=3), capacity=100
        )
        for sequence in range(30):
            self.assertIsNotNone(processor.process(frame(sequence, 1.0)))

        self.assertIsNone(processor.process(frame(30, 1000.0)))
        self.assertEqual(processor.quality, DataQuality.DEGRADED)
        self.assertEqual(processor.quality_reason, "motion_or_signal_artifact")
        self.assertEqual(processor.waveforms(60.0)["global"].size, 30)

    def test_spatial_map_is_reduced_to_synchronized_global_and_eight_rois(self):
        processor = AerationProcessor(capacity=10)
        image = tuple(tuple(1.0 for _ in range(32)) for _ in range(32))
        source = EITFrame(
            sequence_number=0,
            timestamp_utc=NOW,
            belt_index=0,
            global_impedance=-123.0,
            roi_impedance=(-123.0,) * 8,
            reconstructed_delta_z=image,
            quality=DataQuality.VALID,
            simulated=True,
        )

        accepted = processor.process(source)

        self.assertIsNotNone(accepted)
        self.assertGreater(accepted.global_impedance, 0.0)
        self.assertAlmostEqual(
            accepted.global_impedance, sum(accepted.roi_impedance), places=12
        )
        self.assertNotEqual(accepted.global_impedance, source.global_impedance)

    def test_same_interval_and_version_produce_identical_result(self):
        params = AerationAlgorithmParameters(sample_rate_hz=25.0, smoothing_samples=1)
        processor = AerationProcessor(params, capacity=1000)
        for sequence in range(500):
            value = 10.0 + 2.0 * np.sin(2.0 * np.pi * 0.25 * sequence / 25.0)
            processor.process(frame(sequence, value))

        first = processor.result(start_time_seconds=4.0, end_time_seconds=16.0)
        second = processor.result(start_time_seconds=4.0, end_time_seconds=16.0)

        self.assertEqual(first, second)
        self.assertEqual(first.algorithm_version, params.version)
        self.assertEqual(first.parameters, params)
        self.assertEqual(first.interval_start_seconds, 4.0)
        self.assertEqual(first.interval_end_seconds, 16.0)
        self.assertEqual(first.analyzed_sample_count, 301)

    def test_latest_complete_cycles_can_be_selected_reproducibly(self):
        params = AerationAlgorithmParameters(sample_rate_hz=25.0, smoothing_samples=1)
        processor = AerationProcessor(params, capacity=1000)
        for sequence in range(500):
            value = 10.0 + 2.0 * np.sin(2.0 * np.pi * 0.25 * sequence / 25.0)
            processor.process(frame(sequence, value))

        processor.configure_analysis(window_seconds=30.0, cycle_count=3)
        selected = processor.result()

        self.assertEqual(selected.selected_cycle_count, 3)
        self.assertEqual(selected.complete_cycle_count, 3)
        self.assertEqual(selected.quality, DataQuality.VALID)
        self.assertLess(selected.analyzed_sample_count, 20 * 25)
        self.assertEqual(selected, processor.result())

    def test_cycle_selection_reports_insufficient_data_instead_of_fabricating(self):
        processor = AerationProcessor(
            AerationAlgorithmParameters(smoothing_samples=1), capacity=100
        )
        for sequence in range(50):
            processor.process(frame(sequence, 1.0))
        processor.configure_analysis(window_seconds=2.0, cycle_count=3)

        result = processor.result()

        self.assertEqual(result.quality, DataQuality.UNAVAILABLE)
        self.assertEqual(result.quality_reason, "insufficient_complete_cycles")
        self.assertEqual(result.selected_cycle_count, 3)


if __name__ == "__main__":
    unittest.main()
