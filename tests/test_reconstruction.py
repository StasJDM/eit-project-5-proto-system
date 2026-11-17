import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from app.application import EventBus, MonitoringService
from app.data_sources import JSONMeasurementDataSource, RawMeasurementFrame
from app.domain import AcquisitionSettings, DataQuality
from app.reconstruction import (
    CompleteElectrodeModel,
    DEFAULT_MEASUREMENT_PROTOCOL,
    MeshDensity,
    RawFrameReconstructor,
    MeasurementProtocol,
    generate_mesh,
    ellipse_profile,
    geometry_profile,
)


NOW = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)


class ReconstructionCoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = geometry_profile("adult")
        cls.mesh = generate_mesh(
            cls.profile, DEFAULT_MEASUREMENT_PROTOCOL, MeshDensity.LOW
        )
        cls.model = CompleteElectrodeModel(
            cls.mesh, cls.profile, DEFAULT_MEASUREMENT_PROTOCOL
        )

    def test_adjacent_protocol_and_fem_jacobian_have_expected_dimensions(self):
        self.assertEqual(DEFAULT_MEASUREMENT_PROTOCOL.electrode_count, 16)
        self.assertEqual(DEFAULT_MEASUREMENT_PROTOCOL.expected_channel_count, 208)
        self.assertEqual(self.mesh.elements.shape, (224, 3))
        jacobian = self.model.jacobian(current_amperes=0.005)
        self.assertEqual(jacobian.shape, (208, 224))
        self.assertTrue(np.isfinite(jacobian).all())
        self.assertFalse(self.model.validated_for_real_data)

    def test_selectable_protocol_hypotheses_keep_208_channels_but_change_mapping(self):
        sequences = (
            "adjacent_fixed",
            "adjacent_rotating",
            "adjacent_reciprocal",
            "adjacent_reversed",
        )
        channel_maps = []
        for sequence in sequences:
            protocol = MeasurementProtocol.adjacent_16_hypothesis(
                electrode_order="sternum_cw",
                measurement_sequence=sequence,
            )
            self.assertEqual(protocol.expected_channel_count, 208)
            self.assertEqual(protocol.electrodes[0].angle_degrees, 90.0)
            self.assertEqual(protocol.electrodes[1].angle_degrees, 67.5)
            channel_maps.append(tuple(
                (channel.drive_pair, channel.measurement_pair)
                for channel in protocol.channels
            ))
        self.assertEqual(len(set(channel_maps)), len(sequences))

    def test_reconstructor_uses_protocol_choices_from_settings(self):
        settings = AcquisitionSettings(
            electrode_order="sternum_ccw",
            measurement_sequence="adjacent_reversed",
        )
        reconstructor = RawFrameReconstructor(settings)
        self.assertIn("sternum_ccw", reconstructor.diagnostics.protocol_id)
        self.assertIn("adjacent_reversed", reconstructor.diagnostics.protocol_id)

    def test_ellipse_profile_changes_mesh_and_reconstruction_diagnostics(self):
        profile = ellipse_profile(
            width_m=0.30,
            height_m=0.21,
            profile_id="test-ellipse-v1",
            display_name="Test ellipse",
        )
        mesh = generate_mesh(profile, DEFAULT_MEASUREMENT_PROTOCOL, MeshDensity.LOW)
        boundary = mesh.nodes[mesh.boundary_edges.ravel()]
        span = np.ptp(boundary, axis=0)
        self.assertAlmostEqual(float(span[0]), 0.30, places=6)
        self.assertAlmostEqual(float(span[1]), 0.21, places=6)
        reconstructor = RawFrameReconstructor(AcquisitionSettings(), geometry=profile)
        self.assertEqual(
            reconstructor.diagnostics.geometry_profile_id, "test-ellipse-v1"
        )

    def test_streaming_raw_frames_produce_finite_non_mock_reconstruction(self):
        settings = AcquisitionSettings(
            injection_current_ma=5.0,
            sample_rate_hz=3.0,
        )
        reconstructor = RawFrameReconstructor(settings, reference_seconds=1.0)
        background = np.ones(self.mesh.element_count)
        changed = background.copy()
        centers = self.mesh.nodes[self.mesh.elements].mean(axis=1)
        changed[np.linalg.norm(centers - np.array((0.055, 0.035)), axis=1) < 0.035] += 0.2
        reference_values = self.model.solve(
            background, current_amperes=0.005
        ).measurements
        changed_values = self.model.solve(
            changed, current_amperes=0.005
        ).measurements

        outputs = []
        for sequence, values in enumerate(
            (reference_values, reference_values, reference_values, changed_values)
        ):
            outputs.append(reconstructor.process(RawMeasurementFrame(
                sequence_number=sequence,
                timestamp_utc=NOW + timedelta(seconds=sequence / 3),
                channel_values=tuple(float(value) for value in values),
            )))

        self.assertIsNone(outputs[0])
        self.assertIsNone(outputs[1])
        result = outputs[-1]
        self.assertIsNotNone(result)
        self.assertEqual(len(result.reconstructed_delta_z), 64)
        image = np.asarray(result.reconstructed_delta_z)
        absolute = np.asarray(result.absolute_conductivity)
        self.assertTrue(np.isfinite(image).all())
        self.assertEqual(absolute.shape, (64, 64))
        self.assertTrue(np.isfinite(absolute).all())
        self.assertTrue(np.all(absolute >= 0.0))
        self.assertGreater(float(np.max(absolute)), 1.0)
        self.assertGreater(float(np.max(np.abs(image))), 0.0)
        self.assertEqual(result.quality, DataQuality.VALID)
        self.assertTrue(reconstructor.diagnostics.ready)
        self.assertFalse(reconstructor.diagnostics.assumptions_confirmed)
        fixed_normalization = (
            reconstructor._absolute_center,
            reconstructor._absolute_scale,
        )
        stronger = background.copy()
        stronger[np.linalg.norm(centers - np.array((0.055, 0.035)), axis=1) < 0.035] += 0.4
        stronger_values = self.model.solve(
            stronger, current_amperes=0.005
        ).measurements
        reconstructor.process(RawMeasurementFrame(
            sequence_number=4,
            timestamp_utc=NOW + timedelta(seconds=4 / 3),
            channel_values=tuple(float(value) for value in stronger_values),
        ))
        self.assertEqual(
            (reconstructor._absolute_center, reconstructor._absolute_scale),
            fixed_normalization,
        )


class RealJSONReconstructionIntegrationTest(unittest.TestCase):
    def test_looped_default_recording_keeps_all_trend_metrics_available(self):
        source = JSONMeasurementDataSource(
            Path("examples/fromfile/test_3.json"),
            simulated=True,
            loop_playback=True,
        )
        monitoring = MonitoringService(
            source,
            EventBus(),
            settings=source.suggested_settings,
            roi_count=10,
        )
        samples = []
        monitoring.subscribe_trend_samples(samples.append)
        source.connect()
        source.configure(source.suggested_settings)
        source.start()
        try:
            # More than two 15-second trend intervals and several source loops.
            for _index in range(750):
                monitoring._accept_frame(source.read_frame())
        finally:
            source.stop()
            source.disconnect()

        values = dict(samples[-1].metric_values)
        self.assertEqual(samples[-1].quality, DataQuality.VALID)
        for code in (
            "eeli_au",
            "eili_au",
            "tvi_au",
            "mvi_au_per_min",
            "rr_bpm",
            "right_left_ratio",
            "ventral_dorsal_ratio",
            "right_percent",
            "left_percent",
        ):
            with self.subTest(metric=code):
                self.assertIsNotNone(values[code])

    def test_test_1_produces_positive_absolute_relative_conductivity(self):
        source = JSONMeasurementDataSource(Path("examples/fromfile/test_1.json"))
        reconstructor = RawFrameReconstructor(source.suggested_settings)
        reconstructor.prime_reference(source.reconstruction_reference_frames)

        result = reconstructor.process(source.recording.frames[0])

        self.assertIsNotNone(result)
        absolute = np.asarray(result.absolute_conductivity)
        positive = absolute[absolute > 0.0]
        self.assertEqual(absolute.shape, (64, 64))
        self.assertTrue(np.isfinite(absolute).all())
        self.assertGreater(positive.size, 0)
        self.assertAlmostEqual(float(np.median(positive)), 1.0, delta=0.01)

    def test_provided_real_json_reconstructs_all_post_reference_frames(self):
        path = Path(
            "/Users/stas/my/eit/eit_project_6_air/measurments/sample_sitting.json"
        )
        if not path.is_file():
            self.skipTest("provided sibling JSON fixture is not installed")
        source = JSONMeasurementDataSource(path)
        reconstructor = RawFrameReconstructor(source.suggested_settings)
        reconstructor.prime_reference(source.reconstruction_reference_frames)
        reconstructed = [
            result
            for frame in source.recording.frames
            if (result := reconstructor.process(frame)) is not None
        ]

        self.assertEqual(len(source.recording.frames), 98)
        self.assertEqual(len(reconstructed), 98)
        self.assertEqual(source.recording.excitation_current_ma, 5.0)
        self.assertEqual(
            np.asarray(reconstructed[-1].reconstructed_delta_z).shape,
            (64, 64),
        )
        self.assertEqual(
            np.asarray(reconstructed[-1].absolute_conductivity).shape,
            (64, 64),
        )
        self.assertTrue(reconstructor.diagnostics.ready)
        self.assertEqual(reconstructor.diagnostics.active_channel_count, 208)


if __name__ == "__main__":
    unittest.main()
