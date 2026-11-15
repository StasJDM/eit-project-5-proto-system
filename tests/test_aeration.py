import unittest
from datetime import datetime, timezone

import numpy as np

from app.application import (
    ALGORITHM_VERSION,
    DERIVATIVE_ALGORITHM_VERSION,
    LEGACY_ALGORITHM_VERSION,
    AerationAlgorithmParameters,
    AerationProcessor,
    calculate_breathing_velocity,
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
    def test_displayed_velocity_uses_the_detection_derivative(self):
        fs = 25.0
        time = np.arange(0.0, 12.0, 1.0 / fs)
        signal = 10.0 + 2.0 * np.sin(2.0 * np.pi * 0.25 * time)
        velocity = calculate_breathing_velocity(
            signal, AerationAlgorithmParameters(sample_rate_hz=fs)
        )

        self.assertEqual(velocity.shape, signal.shape)
        expected_sign = np.cos(2.0 * np.pi * 0.25 * time)
        self.assertGreater(np.corrcoef(velocity[25:-25], expected_sign[25:-25])[0, 1], 0.99)

    def test_mad_mean_is_default_and_previous_detectors_remain_versioned(self):
        current = AerationAlgorithmParameters()
        derivative = AerationAlgorithmParameters(peak_detection_method="derivative")
        legacy = AerationAlgorithmParameters(peak_detection_method="legacy")

        self.assertEqual(current.peak_detection_method, "mad_mean")
        self.assertEqual(current.version, ALGORITHM_VERSION)
        self.assertEqual(derivative.version, DERIVATIVE_ALGORITHM_VERSION)
        self.assertEqual(legacy.version, LEGACY_ALGORITHM_VERSION)

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
        self.assertAlmostEqual(result.tvi_au, 4.0, delta=0.05)
        self.assertAlmostEqual(
            result.minute_ventilation_au_per_min, 60.0, delta=0.75
        )
        self.assertEqual(result.status_for("mvi").quality, DataQuality.VALID)
        self.assertAlmostEqual(sum(result.roi_tvi_au), result.tvi_au, places=6)
        self.assertAlmostEqual(result.right_percent, 50.0, places=6)
        self.assertAlmostEqual(result.left_percent, 50.0, places=6)
        self.assertAlmostEqual(result.right_left_ratio, 1.0, places=6)
        self.assertAlmostEqual(result.ventral_dorsal_ratio, 7.0 / 3.0, places=6)
        self.assertEqual(
            tuple(round(value, 6) for value in result.roi_percent),
            (20.0, 15.0, 10.0, 5.0, 20.0, 15.0, 10.0, 5.0),
        )

    def test_mad_mean_averages_a_peak_zone_instead_of_using_one_outlier(self):
        fs = 25.0
        time = np.arange(0.0, 24.0, 1.0 / fs)
        phase = np.mod(time, 4.0)
        breathing = np.piecewise(
            phase,
            [
                phase < 0.5,
                (phase >= 0.5) & (phase < 2.0),
                (phase >= 2.0) & (phase < 2.5),
                phase >= 2.5,
            ],
            [
                8.0,
                lambda value: 8.0 + (value - 0.5) * 4.0 / 1.5,
                12.0,
                lambda value: 12.0 - (value - 2.5) * 4.0 / 1.5,
            ],
        )
        breathing[np.argmin(np.abs(time - 22.2))] = 13.0
        weights = (4, 3, 2, 1, 4, 3, 2, 1)
        rois = [breathing * weight / sum(weights) for weight in weights]

        averaged = calculate_aeration_metrics(
            breathing,
            rois,
            AerationAlgorithmParameters(sample_rate_hz=fs),
        )
        point_peak = calculate_aeration_metrics(
            breathing,
            rois,
            AerationAlgorithmParameters(
                sample_rate_hz=fs, peak_detection_method="legacy"
            ),
        )

        self.assertAlmostEqual(averaged.respiratory_rate_bpm, 15.0)
        self.assertGreater(averaged.eili_au, 12.0)
        self.assertLess(averaged.eili_au, point_peak.eili_au)
        self.assertAlmostEqual(averaged.eili_au, 12.0 + 1.0 / 7.0)

    def test_derivative_detector_ignores_small_zero_crossing_jitter(self):
        fs = 25.0
        time = np.arange(0.0, 24.0, 1.0 / fs)
        breathing = (
            10.0
            + 2.0 * np.sin(2.0 * np.pi * 0.25 * time)
            + 0.04 * np.sin(2.0 * np.pi * 4.3 * time)
            + 0.02 * np.sin(2.0 * np.pi * 7.1 * time)
        )
        weights = (4, 3, 2, 1, 4, 3, 2, 1)
        rois = [breathing * weight / sum(weights) for weight in weights]

        result = calculate_aeration_metrics(
            breathing,
            rois,
            AerationAlgorithmParameters(sample_rate_hz=fs),
        )

        self.assertEqual(result.algorithm_version, ALGORITHM_VERSION)
        self.assertAlmostEqual(result.respiratory_rate_bpm, 15.0, places=6)
        self.assertAlmostEqual(result.tvi_au, 4.0, delta=0.15)
        self.assertEqual(result.complete_cycle_count, 5)

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
        self.assertIsNone(result.minute_ventilation_au_per_min)
        self.assertEqual(result.quality, DataQuality.VALID)
        self.assertEqual(result.status_for("rr").quality, DataQuality.UNAVAILABLE)
        self.assertEqual(result.status_for("mvi").quality, DataQuality.UNAVAILABLE)
        self.assertEqual(
            result.status_for("rr").reason, "insufficient_complete_cycles"
        )
        self.assertEqual(result.status_for("tvi").quality, DataQuality.VALID)

    def test_source_quality_is_temporarily_ignored_for_available_metrics(self):
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

        self.assertEqual(result.quality, DataQuality.VALID)
        for metric in ("rr", "tvi", "eeli", "eili", "r_pct", "roi_1"):
            self.assertEqual(result.status_for(metric).quality, DataQuality.VALID)
            self.assertIsNone(result.status_for(metric).reason)

    def test_processor_temporarily_accepts_a_large_artifact_as_valid(self):
        processor = AerationProcessor(
            AerationAlgorithmParameters(smoothing_samples=3), capacity=100
        )
        for sequence in range(30):
            self.assertIsNotNone(processor.process(frame(sequence, 1.0)))

        self.assertIsNotNone(processor.process(frame(30, 1000.0)))
        self.assertEqual(processor.quality, DataQuality.VALID)
        self.assertIsNone(processor.quality_reason)
        self.assertEqual(processor.waveforms(60.0)["global"].size, 31)

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
