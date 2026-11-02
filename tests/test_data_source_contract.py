import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.data_sources import (
    DataSourceError,
    DataSourceEventType,
    DataSourceSequenceError,
    DataSourceTimingPolicy,
    FrameSequenceTracker,
    JSONMeasurementFormatError,
    SimulationDataSource,
    TimestampSource,
    load_json_measurement_recording,
    parse_json_measurement_recording,
)


START = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)


def frame(value=0.1):
    return {"0": [value] * 208}


class DataSourceContractTest(unittest.TestCase):
    def test_all_bundled_fromfile_examples_satisfy_the_strict_contract(self):
        paths = sorted(Path("examples/fromfile").glob("*.json"))
        self.assertGreaterEqual(len(paths), 8)
        for path in paths:
            with self.subTest(path=path.name):
                recording = load_json_measurement_recording(path, simulated=True)
                self.assertGreaterEqual(len(recording.frames), 1)
                self.assertTrue(all(
                    len(frame.channel_values) == 208
                    for frame in recording.frames
                ))

    def test_observed_hardware_json_and_param_are_normalized(self):
        recording = parse_json_measurement_recording(
            {"0": frame(), "1": frame(0.2), "param": "1_1_100_5.000000"},
            fallback_frame_rate_hz=25.0,
            recording_started_at_utc=START,
        )

        self.assertEqual(len(recording.frames), 2)
        self.assertEqual(recording.frames[1].sequence_number, 1)
        self.assertAlmostEqual(
            (recording.frames[1].timestamp_utc - START).total_seconds(),
            0.04,
        )
        self.assertEqual(recording.frames[0].timestamp_source, TimestampSource.SYNTHESIZED)
        self.assertEqual(recording.excitation_frequency_khz, 100.0)
        self.assertEqual(recording.excitation_current_ma, 5.0)
        self.assertEqual(recording.channel_count, 208)

    def test_generator_and_monitoring_metadata_variants_are_supported(self):
        generated = parse_json_measurement_recording({
            "0": frame(-0.1),
            "_metadata": {
                "n_electrodes": 16,
                "n_channels": 208,
                "current_pattern": "adjacent",
                "fps": 20.0,
            },
        }, simulated=True)
        recorded = parse_json_measurement_recording({
            "0": [0.1] * 208,
            "metadata": {
                "frame_rate_hz": 10.0,
                "recorded_at": "2026-10-25T13:00:00+03:00",
            },
        })

        self.assertEqual(generated.frame_rate_hz, 20.0)
        self.assertTrue(generated.frames[0].simulated)
        self.assertEqual(recorded.frames[0].timestamp_utc, START)
        self.assertEqual(recorded.frames[0].timestamp_source, TimestampSource.RECORDING_METADATA)

    def test_invalid_width_gap_non_finite_and_duplicate_keys_are_rejected(self):
        bad_payloads = (
            {"0": {"0": [1.0] * 207}},
            {"0": frame(), "2": frame()},
            {"0": {"0": [float("nan")] * 208}},
        )
        for payload in bad_payloads:
            with self.subTest(payload=list(payload)), self.assertRaises(JSONMeasurementFormatError):
                parse_json_measurement_recording(payload)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"0":{"0":[' + ",".join(["1"] * 208) + ']},"0":{"0":[]}}')
            with self.assertRaisesRegex(JSONMeasurementFormatError, "duplicate key"):
                load_json_measurement_recording(path)

    def test_sequence_tracker_reports_loss_and_rejects_reversal(self):
        tracker = FrameSequenceTracker()
        self.assertEqual(tracker.observe(0), 0)
        self.assertEqual(tracker.observe(3), 2)
        self.assertEqual(tracker.expected, 4)
        with self.assertRaises(DataSourceSequenceError):
            tracker.observe(3)

    def test_policy_and_simulator_expose_qt_independent_state_events(self):
        policy = DataSourceTimingPolicy()
        self.assertEqual(policy.max_consecutive_timeouts, 3)
        source = SimulationDataSource(clock=lambda: START)
        source.connect()
        states = source.drain_events()
        self.assertEqual(states[0].type, DataSourceEventType.STATE_CHANGED)
        self.assertEqual(states[0].occurred_at_utc, START)
        self.assertEqual(source.drain_events(), ())
        with self.assertRaises(DataSourceError):
            source.connect("unknown-device")
        self.assertEqual(source.drain_events()[0].type, DataSourceEventType.ERROR)

    def test_neighboring_project_files_match_the_contract_when_available(self):
        sibling_root = Path(__file__).resolve().parents[2]
        candidates = (
            (sibling_root / "eit_project_6_air/measurments/sample_sitting.json", 98, False),
            (sibling_root / "eit_project_2_calculation/m1.json", 93, False),
            (sibling_root / "eit_project_3_measurements_generator/output.json", 1, True),
            (sibling_root / "eit_project_4_monitoring/examples/eupnea.json", 300, True),
        )
        available = [item for item in candidates if item[0].is_file()]
        if not available:
            self.skipTest("neighboring eit_project_* fixtures are not installed")
        for path, expected_frames, simulated in available:
            with self.subTest(path=path.name):
                recording = load_json_measurement_recording(path, simulated=simulated)
                self.assertEqual(len(recording.frames), expected_frames)
                self.assertTrue(all(len(item.channel_values) == 208 for item in recording.frames))


if __name__ == "__main__":
    unittest.main()
