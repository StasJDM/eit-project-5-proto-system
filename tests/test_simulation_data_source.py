import unittest
from datetime import datetime, timezone

from app.data_sources import (
    DataSourceError,
    DataSourceState,
    SimulationDataSource,
    SimulationScenario,
    SimulationScenarioComplete,
)
from app.domain import AcquisitionSettings, DataQuality


FIXED_TIME = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


class SimulationDataSourceTest(unittest.TestCase):
    def make_running_source(self, seed=7):
        source = SimulationDataSource(seed=seed, clock=lambda: FIXED_TIME)
        source.connect()
        source.configure(AcquisitionSettings())
        source.start()
        return source

    def test_lifecycle_and_frame_contract(self):
        source = self.make_running_source()

        first = source.read_frame()
        second = source.read_frame()

        self.assertEqual(source.state, DataSourceState.RUNNING)
        self.assertEqual((first.sequence_number, second.sequence_number), (0, 1))
        self.assertEqual(first.timestamp_utc, FIXED_TIME)
        self.assertEqual(first.belt_index, 0)
        self.assertEqual(len(first.roi_impedance), 8)
        self.assertEqual(len(first.reconstructed_delta_z), 64)
        self.assertTrue(all(len(row) == 64 for row in first.reconstructed_delta_z))
        self.assertEqual(first.quality, DataQuality.VALID)
        self.assertTrue(first.simulated)

        source.stop()
        self.assertEqual(source.state, DataSourceState.CONFIGURED)

    def test_same_seed_produces_same_synchronized_frame(self):
        first = self.make_running_source(seed=11).read_frame()
        second = self.make_running_source(seed=11).read_frame()

        self.assertEqual(first.global_impedance, second.global_impedance)
        self.assertEqual(first.roi_impedance, second.roi_impedance)
        self.assertEqual(
            first.reconstructed_delta_z,
            second.reconstructed_delta_z,
        )

    def test_eupnea_rate_is_calm_and_configurable(self):
        default = SimulationDataSource()
        configured = SimulationDataSource(respiratory_rate_bpm=10.0)

        self.assertEqual(default.respiratory_rate_bpm, 12.0)
        self.assertEqual(configured.respiratory_rate_bpm, 10.0)
        with self.assertRaisesRegex(ValueError, "between 5 and 30"):
            SimulationDataSource(respiratory_rate_bpm=40.0)

    def test_mvp_rejects_unsupported_belt_or_electrode_count(self):
        source = SimulationDataSource()
        source.connect()

        with self.assertRaisesRegex(DataSourceError, "one active"):
            source.configure(AcquisitionSettings(belt_count=2))
        with self.assertRaisesRegex(DataSourceError, "16 electrodes"):
            source.configure(AcquisitionSettings(electrode_count=32))

    def test_mvp_simulator_rejects_unsupported_sample_rate(self):
        source = SimulationDataSource()
        source.connect()

        with self.assertRaisesRegex(DataSourceError, "25 Hz"):
            source.configure(AcquisitionSettings(sample_rate_hz=10.0))

    def test_read_before_start_is_rejected(self):
        with self.assertRaises(DataSourceError):
            SimulationDataSource().read_frame()

    def test_all_named_scenarios_are_deterministic_and_marked_simulated(self):
        for scenario in (
            SimulationScenario.EUPNEA,
            SimulationScenario.APNEA,
            SimulationScenario.TACHYPNEA,
            SimulationScenario.ELECTRODE_LOSS,
            SimulationScenario.NOISE,
        ):
            with self.subTest(scenario=scenario.value):
                first = SimulationDataSource(
                    seed=123, scenario=scenario, duration_seconds=1.0,
                    clock=lambda: FIXED_TIME,
                )
                second = SimulationDataSource(
                    seed=123, scenario=scenario, duration_seconds=1.0,
                    clock=lambda: FIXED_TIME,
                )
                for source in (first, second):
                    source.connect()
                    source.configure(AcquisitionSettings())
                    source.start()
                frames_a = tuple(first.read_frame() for _ in range(20))
                frames_b = tuple(second.read_frame() for _ in range(20))
                self.assertEqual(frames_a, frames_b)
                self.assertTrue(all(item.simulated for item in frames_a))

    def test_fault_scenarios_duration_and_playback_speed_are_controllable(self):
        loss = SimulationDataSource(
            scenario="electrode_loss", duration_seconds=0.4,
            playback_speed=2.0, clock=lambda: FIXED_TIME,
        )
        loss.connect()
        loss.configure(AcquisitionSettings())
        loss.start()
        frames = tuple(loss.read_frame() for _ in range(10))
        self.assertEqual(loss.playback_speed, 2.0)
        self.assertTrue(any(item.quality is DataQuality.DEGRADED for item in frames))
        with self.assertRaises(SimulationScenarioComplete):
            loss.read_frame()

        disconnected = SimulationDataSource(
            scenario="disconnect", duration_seconds=0.4, clock=lambda: FIXED_TIME,
        )
        disconnected.connect()
        disconnected.configure(AcquisitionSettings())
        disconnected.start()
        for _ in range(5):
            disconnected.read_frame()
        with self.assertRaisesRegex(DataSourceError, "connection was lost"):
            disconnected.read_frame()
        self.assertEqual(disconnected.state, DataSourceState.FAILED)


if __name__ == "__main__":
    unittest.main()
